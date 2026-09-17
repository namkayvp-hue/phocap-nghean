from pathlib import Path
from jinja2 import Environment, FileSystemLoader
root=Path(r'C:\\PhoCap\\app\\templates')
env=Environment(loader=FileSystemLoader(str(root)))
env.get_template('partials/dropdown_menu_v1.html')
env.get_template('reports/report_center.html')
print('Jinja: DAT')
