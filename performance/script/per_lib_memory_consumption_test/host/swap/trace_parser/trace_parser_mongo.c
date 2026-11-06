#include "trace_parser.h"

#ifdef MONGO_ENABLE

#include <mongo.h>


void print_int_bson(void *b, const char *name, const uint32_t val)
{
	bson_append_int(b, name, val);
}

void print_long_bson(void *b, const char *name, const uint64_t val)
{
	bson_append_long(b, name, val);
}

void print_float_bson(void *b, const char *name, const float val)
{
	bson_append_double(b, name, val);
}

void print_double_bson(void *b, const char *name, const double val)
{
	bson_append_double(b, name, val);
}

void print_str_bson(void *b, const char *name, const char *val)
{
	bson_append_string(b, name, val);
}


void print_time_bson(void *b, const char *name, const char *val)
{
	/* FIXME think about time packing */
	bson_append_long(b, name, val);
}

void start_array_bson(void *b, const char *name)
{
	bson_append_start_array(b, name);
}

void finish_array_bson(void *b)
{
	bson_append_finish_array(b);
}

void start_object_bson(void *b, const char *name)
{
	bson_append_start_object(b, name);
}

void finish_object_bson(void *b)
{
	bson_append_finish_object(b);
}

void print_msg_hdr_bson(struct msg_hdr *msg_hdr, void *b)
{
	bson_append_int(b, "msg_id", msg_hdr->msg_id);
	bson_append_int(b, "seq_num", msg_hdr->seq_num);
	bson_append_int(b, "time_s", msg_hdr->sec);
	bson_append_int(b, "time_us", msg_hdr->usec);
	bson_append_int(b, "len", msg_hdr->len);
}

char *parse_and_print_value_by_type_bson(char *p, void *b)
{
	char t = *p++;

	uint8_t c;
	uint32_t d;
	uint64_t x;
	uint64_t pp;
	float f;
	double w;
	char *s;

	switch (t) {
	case 'b':
		c = *p;
		p += sizeof(c);
		bson_append_string(b, "arg_type", "b");
		bson_append_int(b, "arg_val", (int)c);
		break;
	case 'c':
		c = *p;
		p += sizeof(c);
		bson_append_string(b, "arg_type", "c");
		bson_append_int(b, "arg_val", c);
		break;
	case 'd':
		d = *(uint32_t *)p;
		p += sizeof(d);
		bson_append_string(b, "arg_type", "d");
		bson_append_int(b, "arg_val", d);
		break;
	case 'x':
		x = *(uint64_t *)p;
		p += sizeof(x);
		bson_append_string(b, "arg_type", "x");
		bson_append_long(b, "arg_val", x);
		break;
	case 'p':
		pp = *(uint64_t *)p;
		p += sizeof(pp);
		bson_append_string(b, "arg_type", "p");
		bson_append_long(b, "arg_val", pp);
		break;
	case 'f':
		f = *(float *)p;
		p += sizeof(f);
		bson_append_string(b, "arg_type", "f");
		bson_append_double(b, "arg_val", f);
		break;
	case 'w':
		w = *(double *)p;
		p += sizeof(w);
		bson_append_string(b, "arg_type", "w");
		bson_append_double(b, "arg_val", w);
		break;
	case 's':
		s = p;
		p += strlen(s) + 1;
		bson_append_string(b, "arg_type", "s");
		bson_append_string(b, "arg_val", s);
		break;
	case 'v':
	case 'n':
		break;
	default:
		printf_deb("  unknown (%c)", t);
		break;
	}

	return p;
}

char *parse_and_print_args_bson(char *buf, void *b)
{
	char *p = buf;
	int i = 0;
	int args_num = 0;

	SANITY_CHECK(buf)

	args_num = *(uint32_t *)p;
	p += sizeof(uint32_t);
	bson_append_int(b, "args_num", args_num);

	bson_append_start_array(b, "args");
	for (i = 0; i < args_num; i++) {
		char arg_ind[10];
		sprintf(arg_ind, "%d", i);
		bson_append_start_object(b, arg_ind);
		p = parse_and_print_value_by_type_bson(p, b);
		bson_append_finish_object(b);
	}
	bson_append_finish_array(b);

	return p;
}

char *parse_and_print_return_bson(char *buf, void *b)
{
	char *p = buf;

	SANITY_CHECK(buf)

	const char *arg_ind = "return";
	bson_append_start_object(b, arg_ind);
	p = parse_and_print_value_by_type_bson(p, b);
	bson_append_finish_object(b);

	return p;
}

static struct conversion_base bson_conversion = {
	.print_int = print_int_bson,
	.print_long = print_long_bson,
	.print_float = print_float_bson,
	.print_double = print_double_bson,
	.print_str = print_str_bson,
	.print_time = print_time_bson,

	.start_array = start_array_bson,
	.finish_array = finish_array_bson,
	.start_object = start_object_bson,
	.finish_object = finish_object_bson,

	.parse_and_print_args = parse_and_print_args_bson,
	.parse_and_print_return = parse_and_print_return_bson,
	.print_msg_hdr = print_msg_hdr_bson,
};

int bson_main(char *buf, FILE * fd)
{
	struct conversion_base *conv_base = &bson_conversion;

	mongo conn[1];
	mongo_write_concern write_concern[1];
	mongo_cursor cursor[1];
	void *b, **bs;
	int b_num = 500; /* size of a batch of documents, */
	/* it is suitable for speeding up without data loss; */
	int b_counter;
	unsigned long total_bcount_exp, total_bcount_real;
	int status;

	status = mongo_client( conn, "127.0.0.1", 27017 );

	if(status != MONGO_OK) {
		switch (conn->err) {
			case MONGO_CONN_NO_SOCKET:  printf( "no socket\n" ); return 1;
			case MONGO_CONN_FAIL:	   printf( "connection failed\n" ); return 1;
			case MONGO_CONN_NOT_MASTER: printf( "not master\n" ); return 1;
			default :break;
		}
	}

	mongo_cmd_drop_collection( conn, "tracedb", "testData", NULL );

	// Initialize the write concern object
	mongo_write_concern_init(write_concern);
	write_concern->w = 1;
	mongo_write_concern_finish(write_concern);

	// Initialize a batch of documents
	bs = (void **)malloc(sizeof(void *) * b_num);
	for (b_counter = 0; b_counter < b_num; b_counter++) {
		b = (void *)malloc(sizeof(bson));
		bs[b_counter] = b;
	}

	b_counter = 0;
	total_bcount_exp = 0;

	while (1) {
		ssize_t rd = fread( buf, 1, MSG_HDR_LEN, fd);
		if (rd == 0) {
			// Insert last portion of documents
			if(b_counter) {
				mongo_insert_batch(conn, "tracedb.testData",
						   (const bson **)bs, b_counter,
						   write_concern, 0);
				total_bcount_exp += b_counter;
			}
			break;
		}
		if (rd < MSG_HDR_LEN) {
			printf("non complete header!\n");
			break;
		}

		char *p = buf;
		struct msg_hdr msg_hdr;

		bson_init(bs[b_counter]);

		p = parse_msg_hdr(p, &msg_hdr);

		conv_base->print_msg_hdr(&msg_hdr, bs[b_counter]);

		rd = fread(buf, 1, msg_hdr.len, fd);
		if (rd < msg_hdr.len) {
			printf("wrong len 1\n");
			break;
		}
		msg_end = buf + msg_hdr.len;

		parse_and_print_msg_payload(buf, &msg_hdr, bs[b_counter], conv_base);

		p += msg_hdr.len;

		if(bson_finish(bs[b_counter]) != BSON_OK) {
			// printf(" Error. ");

			// Do not include a corrupted document in the batch
			continue;
		}

		// Insert the batch if it is full
		if (b_counter == b_num - 1) {
			mongo_insert_batch(conn, "tracedb.testData",
					   (const bson **)bs, b_num,
					   write_concern, 0);
			b_counter = 0;
			total_bcount_exp += b_num;
		} else {
			b_counter++;
		}
	}

	// Count messages stored in the collection
	total_bcount_real = 0;
	mongo_cursor_init(cursor, conn, "tracedb.testData");
	while(mongo_cursor_next(cursor) == MONGO_OK)
		++total_bcount_real;

	//fclose(fd);

	// Destroy objects
	mongo_cursor_destroy(cursor);
	mongo_write_concern_destroy(write_concern);
	for (b_counter = 0; b_counter < b_num; b_counter++) {
		bson_destroy(bs[b_counter]);
	}
	free(bs);
	mongo_destroy(conn);

	if (total_bcount_exp != total_bcount_real)
		printf("ERROR: data loss (read %ld messages, stored in db %ld messages)\n",
			total_bcount_exp, total_bcount_real);
	return 0;
}

int init_bson(struct parse_config_t *conf) {
	conf->main_func = bson_main;
	conf->conv_base = &bson_conversion;
	return 0;
}
#else /* NOMONGO */

int init_bson(struct parse_config_t __unused *conf) {
	printf("bson does not compiled\n");
	return 1;
}
#endif /* NOMONGO */
