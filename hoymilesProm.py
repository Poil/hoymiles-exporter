#!/usr/bin/env python3
import argparse
import asyncio
import logging
import sys
import traceback
from prometheus_client import start_http_server, Gauge
from hoymiles_wifi.dtu import DTU

# Configure logging
logging.basicConfig(
    stream=sys.stdout, 
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def parse_args():
    parser = argparse.ArgumentParser(description="Poll Hoymiles DTU and expose Prometheus metrics")
    parser.add_argument('--dtu-ip', required=True, help="IP address of the Hoymiles DTU")
    parser.add_argument('--enc-rand', required=True, help="Encryption random seed")
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

async def poll_dtu(dtu_ip, enc_rand_bytes, timeout):
    # Initialize once. This maintains the 'sequence' counter 
    # so the DTU knows these are new, unique requests.
    dtu = DTU(
        dtu_ip, 
        enc_rand=enc_rand_bytes, 
        is_encrypted=True, 
        timeout=int(timeout)
    )

    while True:
        try:
            logging.info(f"Polling DTU {dtu_ip}...")
            
            real_data = await asyncio.wait_for(dtu.async_get_real_data_new(), timeout=timeout)
            
            if real_data is None:
                logging.warning("DTU returned None. Retrying...")
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
                        if port and sn:
                            pv_voltage.labels(port_number=port, serial_number=sn).set(getattr(pv, "voltage", 0) / 10)
                            pv_current_amps.labels(port_number=port, serial_number=sn).set(getattr(pv, "current", 0) / 100)
                            pv_current_power.labels(port_number=port, serial_number=sn).set(getattr(pv, "power", 0) / 10)
                            pv_energy_total.labels(port_number=port, serial_number=sn).set(getattr(pv, "energy_total", 0))
                            pv_energy_daily.labels(port_number=port, serial_number=sn).set(getattr(pv, "energy_daily", 0))

        except asyncio.TimeoutError:
            logging.error(f"Timeout: DTU did not respond within {timeout}s")
        except Exception as e:
            logging.error(f"Error polling DTU: {repr(e)}")
            # traceback.print_exc() # Optional: keep if you want deep debugs

        # Wait 60 seconds before next poll
        await asyncio.sleep(60)


async def main():
    args = parse_args()
    
    # Convert the hex string (32 chars) to bytes (16 bytes)
    try:
        enc_rand_bytes = bytes.fromhex(args.enc_rand)
        logging.debug(f"Converted enc_rand to bytes: {len(enc_rand_bytes)} bytes")
    except ValueError:
        logging.error("Invalid enc_rand format! Must be a hex string.")
        sys.exit(1)

    print(f"Starting Prometheus exporter on port {args.port} for DTU {args.dtu_ip}")
    start_http_server(args.port)
    
    await poll_dtu(args.dtu_ip, enc_rand_bytes, args.timeout)

if __name__ == "__main__":
    asyncio.run(main())
