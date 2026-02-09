# hoymiles-exporter

Simple Hoymiles Prometheus exporter based on https://github.com/suaveolent/hoymiles-wifi library

## Usage
* Configure /etc/default/hoymiles-homes (from tpl)
* Copy systemd-unit to /etc/systemd/system/
* Enable and start systemd-unit instance
```
systemctl enable hoymiles-exporter@home
systemctl start hoymiles-exporter@home
```
