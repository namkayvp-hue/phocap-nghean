const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const fields = {};
const field = (id, value='') => fields[id] = {value,disabled:false,style:{setProperty(){}},addEventListener(){}};
const box = (inputs,dataset={}) => ({dataset,hidden:false,style:{setProperty(){}},querySelectorAll:()=>inputs,querySelector:()=>inputs[0]});
field('class_id'); field('class_name_reported','5A'); field('school_name_reported','TH');
field('completed_primary_program','CO'); field('completed_lower_secondary_program','CO');
field('primary_completion_year'); field('lower_secondary_graduation_year');
field('is_repeating_grade','KHONG');
field('study_location_scope','TAI_CHO'); field('study_origin_address'); field('study_destination_address');
field('post_lower_secondary_path','THPT');
fields.post_lower_secondary_path_wrap=box([fields.post_lower_secondary_path]);
const grades=[box([fields.completed_primary_program],{completionGrade:'5'}),box([fields.completed_lower_secondary_program],{completionGrade:'9'})];
const years=[box([fields.primary_completion_year],{completionYear:'completed_primary_program'}),box([fields.lower_secondary_graduation_year],{completionYear:'completed_lower_secondary_program'})];
fields.study_origin_wrap=box([fields.study_origin_address]); fields.study_destination_wrap=box([fields.study_destination_address]);
fields.age_completion_indicators=box([], {birthYear:'2015',schoolYear:'2026-2027'});
fields.age_completion_fields={appendChild(node){node.parentNode=this;}};
const events={};
vm.runInNewContext(fs.readFileSync('app/static/js/year_record_school_details.js','utf8'),{
 document:{getElementById:id=>fields[id],addEventListener:(name,handler)=>events[name]=handler,
 querySelectorAll:selector=>selector==='[data-completion-grade]'?grades:selector==='[data-completion-year]'?years:[...grades,...years]},
 setTimeout:callback=>callback(),Date,
});
assert.equal(grades[0].hidden,false);assert.equal(fields.primary_completion_year.value,'2026');
for (const age of [10,11,14,15,18,19]) {
 fields.age_completion_indicators.dataset.birthYear=String(2026-age);events.change();
 assert.equal(grades[0].hidden,!(age>=11&&age<=14));
 assert.equal(grades[1].hidden,!(age>=15&&age<=18));
}
fields.age_completion_indicators.dataset.birthYear='2010';
fields.class_name_reported.value='10A';fields.school_name_reported.value='THPT';
fields.lower_secondary_graduation_year.value='';events.change();
assert.equal(fields.lower_secondary_graduation_year.value,'2025');
assert.equal(fields.post_lower_secondary_path_wrap.hidden,true);
fields.lower_secondary_graduation_year.value='2024';events.change();
assert.equal(fields.lower_secondary_graduation_year.value,'2024');
fields.is_repeating_grade.value='CO';fields.lower_secondary_graduation_year.value='';events.change();
assert.equal(fields.lower_secondary_graduation_year.value,'');
fields.is_repeating_grade.value='CHUA_XAC_DINH';events.change();
assert.equal(fields.lower_secondary_graduation_year.value,'');
fields.completed_lower_secondary_program.value='KHONG';events.change();
assert.equal(years[1].hidden,true);assert.equal(fields.lower_secondary_graduation_year.required,false);
fields.study_location_scope.value='DI_HOC_NGOAI_TINH';events.change();assert.equal(fields.study_destination_wrap.hidden,false);
fields.study_location_scope.value='NOI_KHAC_DEN';events.change();assert.equal(fields.study_origin_wrap.hidden,false);assert.equal(fields.study_destination_wrap.hidden,true);
fields.age_completion_indicators.dataset.birthYear='2009';
fields.class_name_reported.value='Lop 12';
fields.is_repeating_grade.value='CHUA_XAC_DINH';
fields.completed_lower_secondary_program.value='CO';
fields.lower_secondary_graduation_year.value='';events.change();
assert.equal(fields.lower_secondary_graduation_year.value,'2024');
fields.is_repeating_grade.value='CO';fields.lower_secondary_graduation_year.value='';events.change();
assert.equal(fields.lower_secondary_graduation_year.value,'');
console.log('Age boundaries, automatic years, repeating, saved years and addresses: OK');
