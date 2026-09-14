# -*- coding: utf-8 -*-
from pathlib import Path
import shutil, re, datetime, sys

VERSION = "BAI 13B-12 V2.4.4.6.2 - SUA LOI 2.4.3"
ROOT = Path(r"C:\PhoCap")
TARGET = ROOT / "app" / "templates" / "surveys" / "multi_year_trend.html"
BACKUP_ROOT = ROOT / "backups"

NEW_START = '<!-- === BAI_13B_12_V2_4_4_6_2_ROADMAP_SIM_START === -->'
NEW_END = '<!-- === BAI_13B_12_V2_4_4_6_2_ROADMAP_SIM_END === -->'
BAD_START = '<!-- === BAI_13B_12_V2_4_4_6_1_ROADMAP_SIM_START === -->'
BAD_END = '<!-- === BAI_13B_12_V2_4_4_6_1_ROADMAP_SIM_END === -->'
OLD_START = '<!-- === BAI_13B_11_17_V1_DASHBOARD_UI_START === -->'
OLD_END = '<!-- === BAI_13B_11_17_V1_DASHBOARD_UI_END === -->'

DASHBOARD_BLOCK = '<!-- === BAI_13B_12_V2_4_4_6_2_ROADMAP_SIM_START === -->\n<section id="pcgd-recognition-dashboard" class="pcgd-db">\n  <div class="pcgd-db-head">\n    <div>\n      <span class="pcgd-simulation-badge">MÔ PHỎNG THEO LỘ TRÌNH · KHÔNG PHẢI KẾT QUẢ CÔNG NHẬN</span>\n      <div class="pcgd-db-kicker">2.4.3 · DASHBOARD LỘ TRÌNH VÀ XU HƯỚNG</div>\n      <h1>Dashboard mô phỏng lộ trình PCGDMN 2026–2030</h1>\n      <p>\n        Mô phỏng xu hướng theo năm đăng ký trong lộ trình PCGDMN 2026–2030; dữ liệu điều tra hiện có chỉ dùng làm thông tin tham chiếu, không thay thế kết luận công nhận thực tế.\n      </p>\n    </div>\n    <div class="pcgd-db-tabs">\n      <button type="button" class="pcgd-tab active" data-tab="roadmap">\n        Trẻ 3–5 tuổi · Lộ trình\n      </button>\n      <button type="button" class="pcgd-tab" data-tab="five">\n        Trẻ 5 tuổi · NĐ20\n      </button>\n    </div>\n  </div>\n\n  <div id="pcgd-db-warning" class="pcgd-db-warning" hidden></div>\n\n  <div class="pcgd-db-cards">\n    <article><span>Tổng xã/phường</span><strong id="db-total">–</strong></article>\n    <article><span>Đăng ký theo lộ trình năm nay</span><strong id="db-due">–</strong></article>\n    <article><span>Điều tra hoàn thành</span><strong id="db-complete">–</strong></article>\n    <article><span>Đủ 2 chỉ tiêu trẻ 5 tuổi</span><strong id="db-five-pass">–</strong></article>\n    <article><span>Xã ĐBKK</span><strong id="db-special">–</strong></article>\n  </div>\n\n  <div class="pcgd-db-grid">\n    <section class="pcgd-panel">\n      <div class="pcgd-panel-head">\n        <div>\n          <small>MÔ PHỎNG KẾ HOẠCH 2026–2030</small>\n          <h2>Phân bố xã/phường theo năm đăng ký</h2>\n        </div>\n        <span id="db-roadmap-loaded" class="pcgd-pill">–</span>\n      </div>\n      <div id="db-roadmap-bars" class="pcgd-bars"></div>\n    </section>\n\n    <section class="pcgd-panel">\n      <div class="pcgd-panel-head">\n        <div>\n          <small>BỘ LỌC</small>\n          <h2>Danh sách xã/phường</h2>\n        </div>\n      </div>\n      <div class="pcgd-filter-row">\n        <input id="db-search" type="search" placeholder="Tìm xã/phường...">\n        <select id="db-year-filter">\n          <option value="">Tất cả năm lộ trình</option>\n          <option value="2026">2026</option>\n          <option value="2027">2027</option>\n          <option value="2028">2028</option>\n          <option value="2029">2029</option>\n          <option value="2030">2030</option>\n          <option value="NONE">Chưa có lộ trình</option>\n        </select>\n        <select id="db-status-filter">\n          <option value="">Tất cả trạng thái</option>\n          <option value="DUE">Năm đăng ký</option>\n          <option value="LATE">Quá năm đăng ký</option>\n          <option value="ON_TRACK">Chưa đến năm đăng ký</option>\n          <option value="PASS">5 tuổi đạt 2 chỉ tiêu</option>\n          <option value="FAIL">5 tuổi chưa đạt 2 chỉ tiêu</option>\n          <option value="DATA">Chưa đủ dữ liệu</option>\n        </select>\n      </div>\n    </section>\n  </div>\n\n  <section class="pcgd-panel pcgd-table-panel">\n    <div class="pcgd-panel-head">\n      <div>\n        <small>THEO DÕI CHI TIẾT</small>\n        <h2 id="db-table-title">Lộ trình 3–5 tuổi và mức sẵn sàng dữ liệu</h2>\n      </div>\n      <span id="db-row-count" class="pcgd-pill">0 xã/phường</span>\n    </div>\n\n    <div class="pcgd-table-wrap">\n      <table class="pcgd-table">\n        <thead id="db-table-head"></thead>\n        <tbody id="db-table-body">\n          <tr><td>Đang tải dashboard...</td></tr>\n        </tbody>\n      </table>\n    </div>\n  </section>\n\n  <div class="pcgd-db-notes">\n    <strong>Lưu ý nghiệp vụ:</strong>\n    <span>\n      Đây là xu hướng giả lập theo lộ trình 2026–2030, không phải kết quả công nhận đạt chuẩn thực tế. Kết quả trẻ 5 tuổi chỉ phản ánh các chỉ tiêu trẻ em có nguồn dữ liệu trực tiếp.\n    </span>\n  </div>\n</section>\n\n<style>\n.pcgd-db{margin:0 0 28px;padding:24px;border:1px solid #d9e7f5;border-radius:20px;background:#f7fbff;color:#17324d;box-shadow:0 10px 30px rgba(23,50,77,.08)}\n.pcgd-db *{box-sizing:border-box}\n.pcgd-db-head{display:flex;justify-content:space-between;gap:20px;align-items:flex-start;margin-bottom:18px}\n.pcgd-db-kicker,.pcgd-panel-head small{font-size:12px;font-weight:900;letter-spacing:.08em;color:#0b6dc6}\n.pcgd-db-head h1{margin:4px 0 6px;font-size:30px}\n.pcgd-db-head p{margin:0;color:#64778a;max-width:760px;line-height:1.5}\n.pcgd-simulation-badge{display:inline-flex;margin-bottom:8px;padding:7px 10px;border-radius:999px;background:#fff0c7;color:#7a5700;border:1px solid #efd48c;font-size:11px;font-weight:900;letter-spacing:.03em}\n.pcgd-db-tabs{display:flex;gap:8px;flex-wrap:wrap}\n.pcgd-tab{border:1px solid #c9dceb;background:#fff;color:#24506f;padding:10px 14px;border-radius:999px;font-weight:800;cursor:pointer}\n.pcgd-tab.active{background:#0b6dc6;color:#fff;border-color:#0b6dc6}\n.pcgd-db-warning{padding:10px 12px;margin:0 0 14px;border:1px solid #f1c56d;background:#fff8e8;border-radius:10px;color:#835e12}\n.pcgd-db-cards{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px;margin:16px 0}\n.pcgd-db-cards article{background:#fff;border:1px solid #dce9f4;border-radius:14px;padding:14px}\n.pcgd-db-cards span{display:block;font-size:12px;color:#6c7e8e;font-weight:700}\n.pcgd-db-cards strong{display:block;margin-top:5px;font-size:28px;color:#0757a3}\n.pcgd-db-grid{display:grid;grid-template-columns:1.05fr 1fr;gap:14px;margin:14px 0}\n.pcgd-panel{background:#fff;border:1px solid #dce9f4;border-radius:16px;padding:16px}\n.pcgd-panel-head{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:12px}\n.pcgd-panel-head h2{margin:3px 0 0;font-size:19px}\n.pcgd-pill{display:inline-flex;padding:6px 10px;border-radius:999px;background:#edf6ff;color:#0b5ca8;font-size:12px;font-weight:900}\n.pcgd-bars{display:grid;gap:9px}\n.pcgd-bar-row{display:grid;grid-template-columns:54px 1fr 45px;align-items:center;gap:9px;font-size:13px}\n.pcgd-bar-track{height:11px;border-radius:999px;background:#e8eef5;overflow:hidden}\n.pcgd-bar-fill{height:100%;background:linear-gradient(90deg,#0b6dc6,#5aa9ef);border-radius:999px}\n.pcgd-filter-row{display:grid;grid-template-columns:1.1fr 1fr 1fr;gap:10px}\n.pcgd-filter-row input,.pcgd-filter-row select{width:100%;height:42px;border:1px solid #cbd9e5;border-radius:10px;padding:0 11px;background:#fff}\n.pcgd-table-panel{margin-top:14px}\n.pcgd-table-wrap{overflow:auto;border:1px solid #e1eaf2;border-radius:12px}\n.pcgd-table{width:100%;border-collapse:collapse;min-width:1050px;font-size:13px}\n.pcgd-table th{position:sticky;top:0;background:#edf5fc;color:#25445f;text-align:left;padding:11px;border-bottom:1px solid #d7e3ed;white-space:nowrap}\n.pcgd-table td{padding:11px;border-bottom:1px solid #edf1f5;vertical-align:top}\n.pcgd-table tbody tr:hover{background:#f8fbfe}\n.pcgd-status{display:inline-flex;padding:5px 8px;border-radius:999px;font-size:11px;font-weight:900;white-space:nowrap}\n.pcgd-s-DUE{background:#fff0c7;color:#8a6000}.pcgd-s-LATE,.pcgd-s-FAIL{background:#ffe7e5;color:#a61c12}.pcgd-s-ON_TRACK,.pcgd-s-PASS{background:#e3f7e9;color:#18743b}.pcgd-s-DATA,.pcgd-s-EMPTY,.pcgd-s-NONE{background:#edf1f5;color:#5c6b78}\n.pcgd-metric{font-weight:900}.pcgd-muted{color:#7a8b99;font-size:12px}.pcgd-db-notes{margin-top:14px;padding:12px 14px;border-radius:12px;background:#eef7ff;color:#355c7b;line-height:1.5}\n@media(max-width:1000px){.pcgd-db-cards{grid-template-columns:repeat(2,1fr)}.pcgd-db-grid{grid-template-columns:1fr}.pcgd-db-head{flex-direction:column}.pcgd-filter-row{grid-template-columns:1fr}}\n@media(max-width:600px){.pcgd-db{padding:14px}.pcgd-db-cards{grid-template-columns:1fr}.pcgd-db-head h1{font-size:24px}}\n</style>\n\n<script>\n(function(){\n  const root=document.getElementById(\'pcgd-recognition-dashboard\');\n  if(!root) return;\n\n  let DATA=null;\n  let TAB=\'roadmap\';\n\n  const el=id=>document.getElementById(id);\n  const fmt=v=>(v===null||v===undefined)?\'—\':String(v);\n  const pct=v=>(v===null||v===undefined)?\'—\':Number(v).toFixed(2)+\'%\';\n  const badge=(text,code)=>`<span class="pcgd-status pcgd-s-${code||\'DATA\'}">${text}</span>`;\n\n  function endpoint(){\n    return window.location.pathname\n      .replace(/\\/xu-huong-lien-nam\\/?$/,\'/dashboard-dat-chuan-data\');\n  }\n\n  function renderCards(){\n    const s=DATA.summary||{};\n    el(\'db-total\').textContent=fmt(s.total_communes);\n    el(\'db-due\').textContent=fmt(s.roadmap_current_year);\n    el(\'db-complete\').textContent=fmt(s.survey_complete);\n    el(\'db-five-pass\').textContent=fmt(s.five_child_indicator_pass);\n    el(\'db-special\').textContent=fmt(s.special_difficulty);\n    el(\'db-roadmap-loaded\').textContent=`Lộ trình ${fmt(DATA.roadmap_loaded)}/${fmt(s.total_communes)}`;\n  }\n\n  function renderBars(){\n    const wrap=el(\'db-roadmap-bars\');\n    const counts=DATA.target_counts||{};\n    const years=[\'2026\',\'2027\',\'2028\',\'2029\',\'2030\'];\n    const max=Math.max(1,...years.map(y=>Number(counts[y]||0)));\n    wrap.innerHTML=years.map(y=>{\n      const n=Number(counts[y]||0);\n      const width=Math.round(n*100/max);\n      return `<div class="pcgd-bar-row"><strong>${y}</strong><div class="pcgd-bar-track"><div class="pcgd-bar-fill" style="width:${width}%"></div></div><span>${n} xã</span></div>`;\n    }).join(\'\');\n  }\n\n  function filteredRows(){\n    const q=el(\'db-search\').value.trim().toLowerCase();\n    const year=el(\'db-year-filter\').value;\n    const status=el(\'db-status-filter\').value;\n\n    return (DATA.rows||[]).filter(r=>{\n      if(q && !(`${r.name} ${r.code}`.toLowerCase().includes(q))) return false;\n\n      if(year){\n        if(year===\'NONE\'){\n          if(r.target_year_3_5!==null) return false;\n        }else if(String(r.target_year_3_5)!==year){\n          return false;\n        }\n      }\n\n      if(status){\n        const codes=[r.roadmap_code,r.five_status_code];\n        if(!codes.includes(status)) return false;\n      }\n      return true;\n    });\n  }\n\n  function renderTable(){\n    const rows=filteredRows();\n    el(\'db-row-count\').textContent=`${rows.length} xã/phường`;\n\n    if(TAB===\'roadmap\'){\n      el(\'db-table-title\').textContent=\'Lộ trình 3–5 tuổi và mức sẵn sàng dữ liệu\';\n      el(\'db-table-head\').innerHTML=`<tr>\n        <th>Xã/phường</th><th>Năm đăng ký</th><th>Trạng thái lộ trình</th>\n        <th>Tiến độ điều tra</th><th>Trẻ 3–5 trong dữ liệu</th>\n        <th>Đang học</th><th>Tỷ lệ huy động dữ liệu</th><th>Ghi chú</th>\n      </tr>`;\n      el(\'db-table-body\').innerHTML=rows.map(r=>`<tr>\n        <td><strong>${r.name}</strong><div class="pcgd-muted">${r.code}${r.is_special?\' · ĐBKK\':\'\'}</div></td>\n        <td class="pcgd-metric">${fmt(r.target_year_3_5)}</td>\n        <td>${badge(r.roadmap_status,r.roadmap_code)}</td>\n        <td><strong>${r.completed_forms}/${r.forms}</strong><div class="pcgd-muted">${r.survey_complete?\'Hoàn thành\':\'Chưa hoàn thành\'}</div></td>\n        <td>${r.age_3_5_total}</td>\n        <td>${r.age_3_5_attending}</td>\n        <td class="pcgd-metric">${pct(r.rate_3_5_attending)}</td>\n        <td class="pcgd-muted">Chỉ báo trẻ em; chưa thay kết luận chuẩn toàn diện.</td>\n      </tr>`).join(\'\') || \'<tr><td colspan="8">Không có dữ liệu phù hợp.</td></tr>\';\n    }else{\n      el(\'db-table-title\').textContent=\'Trẻ 5 tuổi – so sánh 2 chỉ tiêu trẻ em theo NĐ20\';\n      el(\'db-table-head\').innerHTML=`<tr>\n        <th>Xã/phường</th><th>Nhóm ngưỡng</th><th>Trẻ 5 tuổi</th>\n        <th>Đến lớp</th><th>Ngưỡng đến lớp</th>\n        <th>Hoàn thành CTGDMN</th><th>Ngưỡng hoàn thành</th><th>Đánh giá</th>\n      </tr>`;\n      el(\'db-table-body\').innerHTML=rows.map(r=>`<tr>\n        <td><strong>${r.name}</strong><div class="pcgd-muted">${r.code}</div></td>\n        <td>${r.is_special?badge(\'ĐBKK\',\'DUE\'):badge(\'Thông thường\',\'DATA\')}</td>\n        <td>${r.age_5_total}</td>\n        <td class="pcgd-metric">${r.age_5_attending} · ${pct(r.rate_5_attending)}</td>\n        <td>≥ ${r.attend_threshold}%</td>\n        <td class="pcgd-metric">${r.age_5_completed} · ${pct(r.rate_5_completed)}</td>\n        <td>≥ ${r.complete_threshold}%</td>\n        <td>${badge(r.five_status,r.five_status_code)}</td>\n      </tr>`).join(\'\') || \'<tr><td colspan="8">Không có dữ liệu phù hợp.</td></tr>\';\n    }\n  }\n\n  function render(){\n    renderCards();\n    renderBars();\n    renderTable();\n    if(DATA.roadmap_warning){\n      const w=el(\'pcgd-db-warning\');\n      w.hidden=false;\n      w.textContent=DATA.roadmap_warning;\n    }\n  }\n\n  root.querySelectorAll(\'.pcgd-tab\').forEach(btn=>{\n    btn.addEventListener(\'click\',()=>{\n      root.querySelectorAll(\'.pcgd-tab\').forEach(b=>b.classList.remove(\'active\'));\n      btn.classList.add(\'active\');\n      TAB=btn.dataset.tab;\n      renderTable();\n    });\n  });\n\n  [\'db-search\',\'db-year-filter\',\'db-status-filter\'].forEach(id=>{\n    el(id).addEventListener(\'input\',renderTable);\n    el(id).addEventListener(\'change\',renderTable);\n  });\n\n  fetch(endpoint(),{headers:{\'Accept\':\'application/json\'},cache:\'no-store\'})\n    .then(r=>r.json())\n    .then(data=>{\n      if(!data.ok) throw new Error(data.message||\'Không tải được dashboard.\');\n      DATA=data;\n      render();\n    })\n    .catch(err=>{\n      el(\'db-table-body\').innerHTML=`<tr><td>Lỗi tải dashboard: ${String(err.message||err)}</td></tr>`;\n    });\n})();\n</script>\n<!-- === BAI_13B_12_V2_4_4_6_2_ROADMAP_SIM_END === -->'

def fail(msg):
    print('[LOI]', msg)
    sys.exit(1)

def remove_block(text, start, end):
    if start not in text:
        return text
    if end not in text:
        fail('Tim thay dau khoi nhung thieu dau ket thuc: ' + start)
    pattern = re.escape(start) + r'.*?' + re.escape(end)
    text, n = re.subn(pattern, '', text, count=1, flags=re.S)
    if n != 1:
        fail('Khong go duoc khoi dashboard can thay.')
    return text

def main():
    print(VERSION)
    print('- Sua Internal Server Error cua muc 2.4.3 sau V2.4.4.6.1.')
    print('- Khoi phuc loi dashboard da tuong thich voi route hien co.')
    print('- Dung lo trinh 2026-2030 de mo phong xu huong.')
    print('- Giu nguyen Ke hoach xu ly truoc khi chot cua V2.4.4.6.1.')
    print('- Khong sua database, router, menu, mobile hay bao cao.\n')

    if not TARGET.is_file():
        fail(f'Khong tim thay {TARGET}')
    original = TARGET.read_text(encoding='utf-8')
    if NEW_START in original:
        print('[THONG TIN] V2.4.4.6.2 da co. Khong cai lap.')
        return

    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = BACKUP_ROOT / f'backup_bai_13b_12_v2_4_4_6_2_{stamp}' / 'app' / 'templates' / 'surveys' / TARGET.name
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TARGET, backup)
    print('[BACKUP]', backup)

    try:
        text = original
        text = remove_block(text, BAD_START, BAD_END)
        text = remove_block(text, OLD_START, OLD_END)

        anchor = '<main class="page-wrap">'
        if anchor not in text:
            raise RuntimeError('Khong tim thay <main class="page-wrap"> trong template.')
        text = text.replace(anchor, anchor + '\n' + DASHBOARD_BLOCK + '\n', 1)

        # Tieu de trang: chi doi neu con ten cu/ban 6.1
        text = text.replace('<p class="trend-eyebrow">BÀI 12D-9</p>', '<p class="trend-eyebrow">2.4.3 · DASHBOARD LỘ TRÌNH VÀ XU HƯỚNG</p>', 1)
        text = text.replace('<h1>Xu hướng phổ cập qua nhiều năm học</h1>', '<h1>Dashboard lộ trình PCGDMN 2026–2030</h1>', 1)

        # Kiem tra Jinja truoc khi ghi de file dang chay.
        try:
            from jinja2 import Environment
            Environment().parse(text)
        except Exception as e:
            raise RuntimeError('Template Jinja khong hop le: ' + str(e))

        if text.count(NEW_START) != 1 or text.count('id="pcgd-recognition-dashboard"') != 1:
            raise RuntimeError('Dashboard bi thieu hoac bi lap.')
        if 'dashboard-dat-chuan-data' not in text:
            raise RuntimeError('Thieu endpoint dashboard-dat-chuan-data trong JavaScript.')

        TARGET.write_text(text, encoding='utf-8')
        print('[CAP NHAT] app\templates\surveys\multi_year_trend.html')
        print('[KIEM TRA] Cu phap Jinja: OK')
        print('[KIEM TRA] Dashboard chi co 1 ban: OK')
        print('[KIEM TRA] Endpoint du lieu cu duoc giu nguyen: OK')
    except Exception as e:
        print('[LOI]', type(e).__name__ + ':', e)
        print('Dang khoi phuc template...')
        TARGET.write_text(original, encoding='utf-8')
        print('[KHOI PHUC]', TARGET)
        fail('Du an da ve trang thai truoc khi cai ban 6.2.')

    print('\n=== CAI DAT THANH CONG ===')
    print('Ban sao an toan:', backup.parent.parent.parent.parent.parent)
    print('Database phocap.db khong bi thay doi.')
    print('Khoi dong lai Uvicorn va mo lai muc 2.4.3.')

if __name__ == '__main__':
    main()
