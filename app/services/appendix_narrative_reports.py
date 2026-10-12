"""Editable Word reports using source appendix text and scoped shared metrics."""
from datetime import date
from io import BytesIO
import json
import re
from zipfile import ZipFile, ZIP_DEFLATED
from xml.sax.saxutils import escape
from app.xmc_appendices import TEMPLATE_DIR
from app.services.compulsory_report_data import Population, school_data, total, disabled
from app.services.xmc_appendix_reports import ratio
from app.services.xmc_rules_353 import LEGAL_BASIS


def display(value):
    if value is None:
        return '[chưa đủ dữ liệu]'
    if isinstance(value,float):
        return f'{value:.2f}'.rstrip('0').rstrip('.').replace('.',',')
    return str(value)


def metric_text(metric):
    n,d,p=metric
    return f'{display(n)}/{display(d)} người; tỷ lệ {display(p)}%' if p is not None else f'{display(n)}/{display(d)} người; tỷ lệ chưa xác định'


def word_document(paragraphs):
    """Small standards-based DOCX, no external library or executable content."""
    body=[]
    for text in paragraphs:
        bold = text.isupper() or bool(re.match(r'^(PHỤ LỤC|Phần |[IVX]+\.)',text))
        body.append('<w:p><w:pPr><w:spacing w:after="120" w:line="276" w:lineRule="auto"/>'+
                    ('<w:keepNext/>' if bold else '')+'</w:pPr><w:r><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/>'+
                    '<w:sz w:val="26"/>'+('<w:b/>' if bold else '')+'</w:rPr><w:t xml:space="preserve">'+escape(text)+'</w:t></w:r></w:p>')
    document='<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'+''.join(body)+'<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1701"/></w:sectPr></w:body></w:document>'
    output=BytesIO()
    with ZipFile(output,'w',ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml','<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        z.writestr('_rels/.rels','<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr('word/document.xml',document)
    output.seek(0)
    return output


def build_narrative(number, db, ctx):
    source=json.loads((TEMPLATE_DIR/f'Phu_luc_{number}.json').read_text(encoding='utf-8'))
    pop=Population(ctx); metrics=pop.indicators()
    year=ctx['reference_year']
    paragraphs=[f"PHỤ LỤC {number} — BẢN TỔNG HỢP CÓ SỐ LIỆU",
                f"Phạm vi: {ctx['label']} · Năm học: {ctx['year'].code} · Xuất ngày {date.today():%d/%m/%Y}",
                'Số liệu tại thời điểm xuất; không phải bản chốt lịch sử ngày 30/9. Các chỗ trống, nhận xét, quyết định công nhận và chữ ký cần đơn vị hoàn thiện.',
                LEGAL_BASIS]
    def filled(text):
        plain=text.lstrip('+- ')
        matches=[('Số trẻ 6 tuổi vào','entry6'),('Số trẻ 11 tuổi hoàn thành','primary11'),
                 ('Số trẻ đến 14 tuổi hoàn thành','primary6_14'),('Số thanh niên, thiếu niên 15 tuổi hoàn thành','secondary15'),
                 ('Số thanh niên, thiếu niên 18 tuổi hoàn thành','secondary18'),
                 ('Số thanh niên, thiếu niên trong độ tuổi 15 đến 18 hoàn thành','secondary15_18'),
                 ('Số thanh niên, thiếu niên trong độ tuổi 15 đến 18 đang học','upper15_18')]
        for prefix,key in matches:
            if plain.startswith(prefix):
                label=text.split(':',1)[0]
                result=label+': '+metric_text(metrics[key])+'.'
                if key=='primary11':
                    result+=' Trẻ 11 tuổi đang học tiểu học: '+metric_text(metrics['primary_study11'])+'.'
                return result
        if plain.startswith('Số trẻ khuyết tật từ 6-14') or plain.startswith('Trẻ khuyết tật có khả năng'):
            return '- Trẻ khuyết tật 6–14 tuổi: '+display(pop.number(6,14,disabled))+'. Có khả năng học tập được tiếp cận giáo dục: '+metric_text(metrics['disabled6_14'])+'.'
        return text
    current_range=(15,35)
    for text in source:
        text=filled(text)
        # Keep headings, qualitative sections and signature blocks from the source.
        if 'Tổng dân số độ tuổi từ 15 đến 35' in text:
            current_range=(15,35)
            text=text.split(':',1)[0]+': '+display(pop.number(15,35))+'.'
        elif 'Tổng dân số độ tuổi từ 15 đến 60' in text:
            current_range=(15,60)
            text=text.split(':',1)[0]+': '+display(pop.number(15,60))+'.'
        elif ('đạt chuẩn biết chữ mức độ' in text and text.lstrip('+- ').startswith('Số người')):
            level=1 if 'mức độ 1' in text else 2
            negative='chưa đạt' in text
            def pred(x):
                value=x[f'g{level}']
                return None if value is None else not value if negative else value
            include_illiterate='Trong đó' in text
            text=text.split(':',1)[0]+': '+metric_text(pop.metric(*current_range,pred))+'.'
            if include_illiterate:
                text+=' Trong đó số người mù chữ: '+metric_text(pop.metric(*current_range,lambda x:x['data'].get('illiterate')))+'.'
        elif 'mù chữ:' in text and text.startswith('Trong đó'):
            text=text.split(':',1)[0]+': '+metric_text(pop.metric(*current_range,lambda x:x['data'].get('illiterate')))+'.'
        if text.startswith(('BIÊN BẢN TỰ KIỂM TRA KẾT QUẢ','Kết quả giáo dục bắt buộc, xóa mù chữ năm')):
            text=re.sub(r'năm\s*[.…]+',f'năm {year}',text)
        paragraphs.append(text)
    paragraphs.extend(['BẢNG ĐỐI CHIẾU SỐ LIỆU TỰ ĐỘNG',
        'Các số liệu dưới đây cùng nguồn với Phụ lục 2 và 3, chỉ bao gồm phạm vi đã chọn.'])
    labels={'entry6':'Trẻ 6 tuổi vào lớp 1','primary11':'Trẻ 11 tuổi hoàn thành tiểu học',
            'primary_study11':'Trẻ 11 tuổi đang học tiểu học','primary6_14':'Trẻ 6–14 tuổi hoàn thành tiểu học',
            'primary14':'Trẻ 14 tuổi hoàn thành tiểu học','disabled6_14':'Trẻ khuyết tật 6–14 có khả năng học được tiếp cận giáo dục',
            'secondary15_18':'Người 15–18 tuổi hoàn thành THCS','secondary15':'Người 15 tuổi hoàn thành THCS',
            'secondary18':'Người 18 tuổi hoàn thành THCS','upper15_18':'Người 15–18 đã/đang học THPT, GDTX hoặc GDNN',
            'disabled11_18':'Người khuyết tật 11–18 có khả năng học được tiếp cận giáo dục'}
    for key,label in labels.items(): paragraphs.append(label+': '+metric_text(metrics[key])+'.')
    for high in (35,60):
        paragraphs.append(f'Dân số 15–{high}: '+display(pop.number(15,high))+'.')
        for level in (1,2):
            paragraphs.append(f'Đạt chuẩn biết chữ mức {level}, tuổi 15–{high}: '+metric_text(pop.metric(15,high,lambda x:x[f'g{level}']))+'.')
    for level,label in [('TH','Tiểu học'),('THCS','THCS')]:
        rows=school_data(db,ctx,level)
        paragraphs.append(f'Đội ngũ và cơ sở vật chất — {label}: {len(rows)} trường có trong phạm vi.')
        for key,title in [('teacher_total','Giáo viên'),('principal','Hiệu trưởng'),('vice_principal','Phó hiệu trưởng'),
                          ('class_total','Số lớp'),('room_permanent','Phòng kiên cố'),('room_semi_permanent','Phòng bán kiên cố'),
                          ('room_temporary','Phòng tạm'),('library_room_count','Thư viện'),('playground_area','Diện tích sân chơi (m²)')]:
            paragraphs.append(title+': '+display(total(data.get(key) for _,data in rows))+'.')
    paragraphs.extend(['THÔNG TIN CẦN HOÀN THIỆN',
        'Nhận xét, ưu điểm, hạn chế, thành phần kiểm tra, kinh phí, văn bản công nhận, phương hướng, kiến nghị và chữ ký: đơn vị bổ sung theo hồ sơ xác nhận.',
        'Chưa đủ dữ liệu không được coi là 0 hoặc chưa đạt. Tỷ lệ không xác định khi thiếu nguồn hoặc mẫu số bằng 0. Không tự kết luận được công nhận đạt chuẩn từ số liệu tính toán.',
        f'Hồ sơ thiếu ngày sinh: {sum(x["age"] is None for x in pop.items)}; thiếu hồ sơ năm học: {sum(x["record"] is None for x in pop.items)}.',
        'Đội ngũ/CSVC dùng dữ liệu đúng năm học; không lấy số liệu năm khác thay thế. Các trường cần xác nhận mức độ đầy đủ của dữ liệu trước khi ký báo cáo.'])
    return word_document(paragraphs)
