// Offline render test: no browser, network or device.
const fs = require('fs'), vm = require('vm'), assert = require('assert');
let status = '失败';
try {
    const source = fs.readFileSync('db/static/js/dashboard.js', 'utf8');
    const context = {escapeHtml: x => String(x)};
    vm.createContext(context);
    vm.runInContext(source.slice(source.indexOf('function memoryGateLabel')), context);
    assert.strictEqual(context.memoryGateLabel('steady_criteria_met'), '满足判据');
    assert.strictEqual(context.memoryGateLabel('fixed_uptime_reached'), '达到固定开机采集时刻');
    const quality = {samples:5,expected_samples:5,invalid_samples:2,
        gates:[{boot_index:1,reason:'steady_criteria_met',uptime:900}],
        per_boot:[{boot_index:1,valid:3,invalid:2,missing:0,invalid_reasons:['bad']}],
        capture_uptimes:[{boot_index:1,sample_index:1,uptime:900,coverage:1,kernel_threads:20,exited_processes:[]}],
        method:{memory_method:'rigor_v1'},transfers:[],cleanup:{verified:true}};
    const html = context.renderMemoryRigor({warnings:['采集时内存未平稳'],quality_a:quality,quality_b:null});
    for (const token of ['role="alert"','采集时内存未平稳','满足判据','3/2/0','内核线程：20','rigor_v1','verified']) assert.ok(html.includes(token),token);
    console.log('UI render checks: 1 passed, 0 failed'); status = '成功';
} finally { console.log('已结束', new Date().toISOString(), '状态', status); }
