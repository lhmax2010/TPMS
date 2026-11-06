var db = connect("localhost:27017/tracedb");
var col = db.testData;

var doc_count = col.count();
if (doc_count == 0) {
	print("Error: empty tracedb/testData collection!");
	exit(1);
} else {
	print("Found " + doc_count + " messages in the tracedb/testData collection");
}


print("error_flag : " + run_analysis());


function run_analysis() {
	var max_addr32 = 0xFFFFFFFF; // 32-bit (4294967295)
	var max_msg_len = 65536;
	var error_flag = 0;

	function print_result(result, test_name) {
		if (result) {
			print('[ \033[01;32mpassed\033[m ] ' + test_name);
		} else {
			print('[ \033[01;31mfailed\033[m ] ' + test_name);
			error_flag = 1;
		}
	}
	
	print("msg_id : " + db.testData.distinct("msg_id"));

	print_result(
	    (col.find( { 'msg_id' : 0x0002 } )
	     .count() > 0),
	    "MSG_TERMINATE exists");

	print_result(
	    col.find( { 'len' : { $gt: max_msg_len } } )
		.count() == 0,
	    "msg length <= " + max_msg_len);
	
	print_result(
	    col.find( { 'payload.pc_address' : { $gt: max_addr32 } } )
		.count() == 0,
	    "payload.pc_address == 32bit value");

	print_result(
	    col.find( { 'payload.caller_pc_address' : { $gt: max_addr32 } } )
		.count() == 0,
	    "payload.caller_pc_address == 32bit value");

	print_result(
	    col.find( { 'payload.cpu_num' : { $gt: 8 } } )
		.count() == 0,
	    "payload.cpu_num <= 8");

	print_result(
	    col.find( { 'payload.args_num' : { $gt: 10 } } )
		.count() == 0,
	    "payload.args_num <= 10");

	print_result(
	    col.find( {"payload.args":
		       { $elemMatch:
			 { arg_type: "p", arg_val: { $gt: 0, $lt: 0x8000 } } } } )
		.count() == 0,
	    "p argument is 0 or greater than 0x8000");

	print_result(
	    col.find( { "payload.pc_address": { $gt: 0xb0000000, $lt: 0xbfffffff },
			"payload.return.arg_type": "p",
			"payload.return.arg_val": { $gt: 0, $lt: 0x8000 } } )
		.count() == 0,
	    "p return is 0 or greater than 0x8000 (userspace)");

	print_result(
	    col.find( { "msg_id": 9,
			"payload.pc_address": { $gt: 0xc0000000, $lt: 0xffffffff },
			"payload.return.arg_type": "d",
			"payload.return.arg_val": { $lt: -1 } } )
		.count() == 0,
	    "d return is 0 or greater than 0x8000 (kernel space)");

	print("Finished");
	
	return error_flag;
}
