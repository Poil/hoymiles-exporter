#!/usr/bin/env python3
import argparse
import asyncio
import logging
import sys
from prometheus_client import start_http_server, Gauge

# Import necessary classes
from hoymiles_wifi.dtu import DTU
from hoymiles_wifi.hoymiles import is_encrypted_dtu

# Configure logging
logging.basicConfig(
    stream=sys.stdout, 
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def parse_args():
    parser = argparse.ArgumentParser(description="Poll Hoymiles DTU and expose Prometheus metrics")
    parser.add_argument('--dtu-ip', required=True, help="IP address of the Hoymiles DTU")
    parser.add_argument('--port', type=int, default=12212, help="Prometheus exporter port")
    parser.add_argument('--timeout', type=float, default=60.0, help="Network timeout in seconds")
    return parser.parse_args()

# --- Metrics Definitions ---
sgs_voltage = Gauge("hoymiles_sgs_voltage", "SGS Voltage (V)", ["serial_number"])
sgs_frequency = Gauge("hoymiles_sgs_frequency", "SGS Frequency (Hz)", ["serial_number"])
sgs_active_power = Gauge("hoymiles_sgs_active_power", "SGS Active Power (W)", ["serial_number"])
sgs_current_amps = Gauge("hoymiles_sgs_current_amps", "SGS Current Amperage (A)", ["serial_number"])
sgs_power_factor = Gauge("hoymiles_sgs_power_factor", "SGS Power Factor (%)", ["serial_number"])
sgs_temperature = Gauge("hoymiles_sgs_temperature", "SGS Temperature (C)", ["serial_number"])

pv_voltage = Gauge("hoymiles_pv_voltage", "PV Voltage (V)", ["serial_number", "port_number"])
pv_current_amps = Gauge("hoymiles_pv_current_amps", "PV Current Amperage (A)", ["serial_number", "port_number"])
pv_current_power = Gauge("hoymiles_pv_current_power", "PV Current Power (W)", ["serial_number", "port_number"])
pv_energy_total  = Gauge("hoymiles_pv_energy_total", "PV Energy Total (Wh)", ["serial_number", "port_number"])
pv_energy_daily = Gauge("hoymiles_pv_energy_daily", "PV Energy Daily (Wh)", ["serial_number", "port_number"])

async def configure_dtu_instance(dtu):
    """
    Uses the existing DTU instance to fetch the encryption key
    and update its internal state.
    """
    logging.info("Handshaking with DTU to check encryption...")
    
    # This command usually works even if we don't have the key yet
    app_info = await dtu.async_app_information_data()
    
    if app_info and app_info.dtu_info.dfs:
        # Check if the device reports as encrypted
        if is_encrypted_dtu(app_info.dtu_info.dfs):
            key = app_info.dtu_info.enc_rand
            logging.info(f"DTU is encrypted. Updating session with key: {key.hex()}")
            
            # Update the EXISTING instance's properties
            # This preserves the sequence number and socket context if reusable
            dtu.is_encrypted = True
            dtu.enc_rand = key
            return True
        else:
            logging.info("DTU is not encrypted.")
            dtu.is_encrypted = False
            dtu.enc_rand = b""
            return True
    
    logging.warning("Handshake failed: Could not retrieve DTU info.")
    return False

async def poll_dtu(dtu_ip, timeout):
    dtu = None

    while True:
        try:
            # --- 1. Session Creation ---
            if dtu is None:
                logging.info(f"Creating new DTU session for {dtu_ip}...")
                # Initialize standard DTU (defaults to no encryption)
                dtu = DTU(dtu_ip, timeout=int(timeout))
                
                # Perform Handshake & Key Update on this specific instance
                success = await configure_dtu_instance(dtu)
                if not success:
                    logging.error("Failed to configure session. Retrying in 15s...")
                    dtu = None # Discard and try again later
                    await asyncio.sleep(15)
                    continue
                
                # CRITICAL: Pause to let the DTU process the handshake before we blast it with data requests
                logging.info("Session ready. Pausing 5s to stabilize connection...")
                await asyncio.sleep(5)

            # --- 2. Data Polling ---
            logging.debug("Requesting Real Data...")
            real_data = await asyncio.wait_for(dtu.async_get_real_data_new(), timeout=timeout)
            
            if real_data is None:
                # If None, the DTU rejected the packet or timed out silently.
                logging.warning("DTU returned None (Request Rejected).")
                # Do NOT invalidate immediately, maybe just a blip. 
                # But if it persists, we might need to re-handshake.
                # For now, we will sleep and retry the same session.
                # If it fails consistently, the 'timeout' exception below usually catches it eventually.
                
                # Optional: Force re-init if you suspect the key expired immediately
                # dtu = None 
            else:
                logging.info("Data received successfully!")
                
                # Process SGS (Inverter) Data
                if hasattr(real_data, 'sgs_data'):
                    for sgs in getattr(real_data, 'sgs_data', []):
                        sn = getattr(sgs, 'serial_number', None)
                        if sn:
                            sgs_voltage.labels(serial_number=sn).set(getattr(sgs, 'voltage', 0) / 10)
                            sgs_frequency.labels(serial_number=sn).set(getattr(sgs, 'frequency', 0) / 100)
                            sgs_active_power.labels(serial_number=sn).set(getattr(sgs, 'active_power', 0) / 10)
                            sgs_current_amps.labels(serial_number=sn).set(getattr(sgs, 'current', 0) / 100)
                            sgs_power_factor.labels(serial_number=sn).set(getattr(sgs, 'power_factor', 0) / 10)
                            sgs_temperature.labels(serial_number=sn).set(getattr(sgs, 'temperature', 0) / 10)

                # Process PV (Panel) Data
                if hasattr(real_data, 'pv_data'):
                    for pv in getattr(real_data, 'pv_data', []):
                        port = str(getattr(pv, 'port_number', "unknown"))
                        sn = getattr(pv, 'serial_number', None)
                        if sn:
                            pv_voltage.labels(port_number=port, serial_number=sn).set(getattr(pv, "voltage", 0) / 10)
                            pv_current_amps.labels(port_number=port, serial_number=sn).set(getattr(pv, "current", 0) / 100)
                            pv_current_power.labels(port_number=port, serial_number=sn).set(getattr(pv, "power", 0) / 10)
                            pv_energy_total.labels(port_number=port, serial_number=sn).set(getattr(pv, "energy_total", 0))
                            pv_energy_daily.labels(port_number=port, serial_number=sn).set(getattr(pv, "energy_daily", 0))

        except (asyncio.TimeoutError, Exception) as e:
            logging.error(f"Communication Error: {e}")
            logging.warning("Invalidating session. Will re-handshake next cycle.")
            dtu = None 
            # Sleep longer on error to avoid hammering a stuck device
            await asyncio.sleep(10)
            continue

        # Standard poll interval
        await asyncio.sleep(60)

async def main():
    args = parse_args()
    print(f"Starting Prometheus exporter on port {args.port} for DTU {args.dtu_ip}")
    start_http_server(args.port)
    await poll_dtu(args.dtu_ip, args.timeout)

if __name__ == "__main__":
    asyncio.run(main())
