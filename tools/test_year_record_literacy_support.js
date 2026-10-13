const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const fields = {};
for (const [id, value] of Object.entries({is_literacy_target:'CO',completed_grade_3:'KHONG',completed_grade_5:'KHONG',
    literacy_learning_support:'CO',literacy_support_period:'9/2026–5/2027',literacy_support_result:'Đang học'})) fields[id]={value,disabled:false};
fields.literacy_support_wrap={querySelectorAll:()=>[fields.literacy_learning_support,fields.literacy_support_period,fields.literacy_support_result]};
fields.literacy_support_details={querySelectorAll:()=>[fields.literacy_support_period,fields.literacy_support_result]};
const events={};
vm.runInNewContext(fs.readFileSync('app/static/js/year_record_literacy_support.js','utf8'),{
    document:{getElementById:id=>fields[id],addEventListener:(name,handler)=>events[name]=handler},setTimeout:callback=>callback()
});
assert.equal(fields.literacy_support_wrap.hidden,false);
assert.equal(fields.literacy_support_details.hidden,false);
fields.literacy_learning_support.value='KHONG'; events.change();
assert.equal(fields.literacy_support_details.hidden,true);
assert.equal(fields.literacy_support_period.disabled,true);
assert.equal(fields.literacy_support_period.value,'9/2026–5/2027');
fields.completed_grade_3.value='CO'; events.change();
assert.equal(fields.literacy_support_wrap.hidden,false);
fields.completed_grade_5.value='CO'; events.change();
assert.equal(fields.literacy_support_wrap.hidden,true);
fields.completed_grade_3.value='KHONG'; events.change();
assert.equal(fields.literacy_support_wrap.hidden,true);
fields.completed_grade_5.value='KHONG'; fields.is_literacy_target.value='KHONG'; events.change();
assert.equal(fields.literacy_support_wrap.hidden,true);
fields.is_literacy_target.value='CO'; fields.completed_grade_3.value='CHUA_XAC_DINH'; events.change();
assert.equal(fields.literacy_support_wrap.hidden,true);
console.log('Literacy support visibility and preservation checks: OK');
