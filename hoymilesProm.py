#!/usr/bin/env python3
import argparse
import asyncio
from prometheus_client import start_http_server, Gauge, Counter
from hoymiles_wifi.dtu import DTU


# Define arguments
def parse_args():
    parser = argparse.ArgumentParser(description="Poll Hoymiles DTU and expose Prometheus metrics")
    parser.add_argument('--dtu-ip', required=True, help="IP address of the Hoymiles DTU")
    return parser.parse_args()

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

async def poll_dtu(dtu_ip):
    dtu = DTU(dtu_ip)

    while True:
        try:
            # Fetch real-time data
            real_data = await dtu.async_get_real_data_new()
            if hasattr(real_data, 'sgs_data'):
                sgs_data = getattr(real_data, 'sgs_data', [])
                for sgs in sgs_data:
                    serial_number = getattr(sgs, 'serial_number', None)
                    if serial_number is not None:
                        voltage = getattr(sgs, 'voltage', 0) / 10
                        frequency = getattr(sgs, 'frequency', 0) / 100
                        active_power = getattr(sgs, 'active_power', 0) / 10
                        current_amps = getattr(sgs, 'current', 0) / 100
                        power_factor = getattr(sgs, 'power_factor', 0) / 10
                        temperature = getattr(sgs, 'temperature', 0) / 10

                        sgs_voltage.labels(serial_number=serial_number).set(voltage)
                        sgs_frequency.labels(serial_number=serial_number).set(frequency)
                        sgs_active_power.labels(serial_number=serial_number).set(active_power)
                        sgs_current_amps.labels(serial_number=serial_number).set(current_amps)
                        sgs_power_factor.labels(serial_number=serial_number).set(power_factor)
                        sgs_temperature.labels(serial_number=serial_number).set(temperature)

            # Check if pv_data exists and iterate over it
            if hasattr(real_data, 'pv_data'):
                pv_data = getattr(real_data, 'pv_data', [])
                for pv in pv_data:
                    port_number = str(getattr(pv, 'port_number', "unknown"))
                    if port_number is not None:
                        serial_number = getattr(pv, 'serial_number', None)
                        voltage = getattr(pv, "voltage", 0) / 10
                        current_amps = getattr(pv, "current", 0) / 100
                        current_power = getattr(pv, "power", 0) / 10
                        energy_total = getattr(pv, "energy_total", 0)
                        energy_daily = getattr(pv, "energy_daily", 0)

                        pv_voltage.labels(port_number=port_number, serial_number=serial_number).set(voltage)
                        pv_current_amps.labels(port_number=port_number, serial_number=serial_number).set(current_amps)
                        pv_current_power.labels(port_number=port_number, serial_number=serial_number).set(current_power)
                        pv_energy_total.labels(port_number=port_number, serial_number=serial_number).set(energy_total)
                        pv_energy_daily.labels(port_number=port_number, serial_number=serial_number).set(energy_daily)

        except Exception as e:
            print(f"Error polling DTU: {e}")

        await asyncio.sleep(60)  # Poll every 30 seconds

async def main():
    # Parse arguments
    args = parse_args()
    dtu_ip = args.dtu_ip

    # Start Prometheus server and begin polling DTU
    start_http_server(12212)
    await poll_dtu(dtu_ip)

if __name__ == "__main__":
    asyncio.run(main())
