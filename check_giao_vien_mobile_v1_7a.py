from pathlib import Path
from jinja2 import Environment, FileSystemLoader
root=Path(r'C:\\PhoCap\\app\\templates')
env=Environment(loader=FileSystemLoader(str(root)))
env.get_template('partials/dropdown_menu_v1.html')
text=(root/'partials'/'dropdown_menu_v1.html').read_text(encoding='utf-8')
for key in ['Phiếu phân công','Hộ dân','Nhập nhanh',"menu_role == 'GIAO_VIEN'"]:
    assert key in text, key
print('Jinja: DAT')
print('Giao vien mobile 3 nut: DAT')
