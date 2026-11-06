//#include <stdio.h>

//#include <stdint.h>
//#include <string.h>
//#include <stdlib.h>
//#include <unistd.h>
//#include <fcntl.h>

//#include "api_id_list.h"
//#include "fd_api_list.h"
#include <arpa/inet.h>
#include <ctype.h>

#include "trace_parser.h"
#include "api_id_list.h"
#include "khash.h"

#include "minilzo.h"

#include "protocol_v3_0.h"
#include "protocol_v4_0.h"
#include "protocol_v4_1.h"
#include "protocol_v4_2.h"

extern uint32_t api_id_list_length;

static int version_number = 40;
const int __MAGIC__DEVICES_COUNT = 3;
int num_of_cpu = 0;
int bin_mode = 0;

KHASH_MAP_INIT_INT(parse_func, parse_and_print_f);
KHASH_MAP_INIT_INT(filter_skip_msg_id, uint32_t);

#define CALLBACKHASH hash
#define FILTER_skip_LIST_HASH skip_list_hash

khash_t(parse_func)* CALLBACKHASH;
khash_t(filter_skip_msg_id)* FILTER_skip_LIST_HASH;

int get_version_number(void)
{
	return version_number;
}

static void add_skip_msg_id(uint32_t id)
{
	khiter_t k;
	int rethash;

	k = kh_get(filter_skip_msg_id, FILTER_skip_LIST_HASH, (uint32_t)id);
	if (k != kh_end(FILTER_skip_LIST_HASH)) {
		/* already in skip list. Do nothing */
		return;
	}

	k = kh_put(filter_skip_msg_id, FILTER_skip_LIST_HASH, (uint32_t)id, &rethash);
	if (rethash != 0) {
		/* succeed to add in hash table */
		kh_value(FILTER_skip_LIST_HASH, k) = id;
		printf("# add to skip list %x\n", id);
	} else {
		// TODO : error handling
	}
}

uint8_t need_to_print_msg_id(uint32_t id)
{
	khiter_t k;

	k = kh_get(filter_skip_msg_id, FILTER_skip_LIST_HASH, (uint32_t)id);
	if (k != kh_end(FILTER_skip_LIST_HASH)) {
		/* in skip list */
		return 0;
	} else {
		return 1;
	}

}

void register_parser(uint32_t id, parse_and_print_f callback)
{
//	printf("id = 0x%04x; p = %p\n", id, callback);

	khiter_t k;
	int rethash;

	k = kh_get(parse_func, CALLBACKHASH, (uint32_t)id);
	if (k != kh_end(CALLBACKHASH)) {
//		printf("reinit id 0x%04x\n", id);
		kh_value(CALLBACKHASH, k) = callback;
		return;
	}

	k = kh_put(parse_func, CALLBACKHASH, (uint32_t)id, &rethash);
	if (rethash != 0) {
		/* succeed to add in hash table */
		kh_value(CALLBACKHASH, k) = callback;
	} else {
		// TODO : error handling
	}
}

void parse_and_print_msg_header(const struct msg_hdr *msg_hdr,
				void *b,
				const struct conversion_base *conv_base)
{
	conv_base->start_object(b, "msg_header");
	conv_base->print_msg_hdr((struct msg_hdr *)msg_hdr, (void *)b);
	conv_base->finish_object(b, "msg_header");

	fflush(stdout);
}

void parse_and_print_msg_payload(char *buf,
				 const struct msg_hdr *msg_hdr,
				 void *b,
				 const struct conversion_base *conv_base)
{
	parse_and_print_f func = NULL;
	khiter_t k;
	uint32_t id = msg_hdr->msg_id;

	conv_base->start_object(b, "payload");

	k = kh_get(parse_func, CALLBACKHASH, (uint32_t)id);
	if (k == kh_end(CALLBACKHASH)) {
		/* there is no entry for key */
		conv_base->print_str(b, "warning", "unknown id");
	} else {
		func = kh_value(CALLBACKHASH, k);
		func(buf, b, conv_base);
	}

	conv_base->finish_object(b, "payload");
	fflush(stdout);
}

void usage(char **argv){
	printf("Usage: %s\n"
	       "-c<num_of_cpu>\n"
	       "[-b (bin format)]\n"
	       "[-t<j/p/t/d> (j-json p-python t-text d-bson)]\n"
	       "[-v<protocol version>]\n"
	       "[-s <skip message id>]\n"
	       "[--uihv_hierarchy uihv parse]\n"
	       "-f <API map file>\n"
	       "<bin trace file>\n",
	       argv[0]);
}

void set_version(int ver)
{
	/* TODO make autoregistration though constructors */
	switch (ver) {
	case 30:
		register_protocol_v3_0();
		break;
	case 40:
		register_protocol_v4_0();
		break;
	case 41:
		register_protocol_v4_1();
		break;
	case 42:
		register_protocol_v4_2();
		break;
	default:
		printf("unknown protocol version %d\n", ver);
		exit(-1);
	}
}

struct parse_config_t parse_config = {
	.main_func = NULL,
	.log = &printf
};

int main(int argc, char **argv)
{
	char buf[64 * 1024];
	FILE * fd;
	char *filename = NULL;
	uint32_t tmp32;
	char tmp_ch;
	char *api_map_list = NULL;

	CALLBACKHASH = kh_init(parse_func);
	FILTER_skip_LIST_HASH = kh_init(filter_skip_msg_id);

	register_protocol_v3_0();

	if (argc < 2) {
		printf("args = %d\n", argc);
		usage(argv);
		return 1;
	}

	while (argc > 1) {
		if (argv[1][0] != '-') {
			filename = argv[1];
			++argv;
			--argc;
			continue;
		}

		switch (argv[1][1]) {
			case 'f':
				++argv;
				--argc;
				api_map_list = strdup(argv[1]);
				break;
			case 'c':
				num_of_cpu = atoi(&argv[1][2]);
				break;
			case 'v':
				version_number = atoi(&argv[1][2]);
				set_version(version_number);
				break;
			case 'b':
				bin_mode = 1;
				break;
			case 's':
				tmp32 = atoi(&argv[1][2]);
				add_skip_msg_id(tmp32);
				break;
			case 't':
				tmp_ch = argv[1][2];
				switch (tmp_ch) {
					case 't':
						init_text(&parse_config);
						break;
					case 'j':
						init_json(&parse_config);
						break;
					case 'p':
						init_py(&parse_config);
						break;
					case 'b':
						init_bson(&parse_config);
						break;
					default:
						printf("# unknown parser type %c\n", tmp_ch);
						usage(argv);
						return 1;
				}
				break;
			case '-':
				if (strcmp("--uihv_hierarchy", argv[1]) == 0) {
					init_uihv(&parse_config);
				} else {
					printf("# unknown param %s\n", argv[1]);
					usage(argv);
					return 1;
				}
				break;
			default:
				printf("# unknown param <%s>\n", argv[1]);
				usage(argv);
				return 1;
		}

		++argv;
		--argc;
	}

	if (num_of_cpu == 0){
		usage(argv);
		return 1;
	}

	/* init default parser */
	if (parse_config.main_func == NULL) {
		if (init_text(&parse_config) != 0) {
			printf("text parse init fail\n");
			return -1;
		}
	}

	if (filename != NULL && strcmp(filename, "")) {
		fd = fopen(filename, "r");
		if (fd == 0) {
			perror("open trace");
			exit(1);
		}
	} else {
		fd = stdin;
		if (fd == 0) {
			perror("open stdin");
			exit(1);
		}
	}

	init_api_id_list(api_map_list);

	/* print parser info */
	parse_config.log("version = %d\n", version_number);
	parse_config.log("cpu num = %d\n", num_of_cpu);
	parse_config.log("api_map_list = <%s>\n", api_map_list);
	parse_config.log("filename = <%s>\n", filename);

	//Init LZO
	if (lzo_init() != LZO_E_OK) {
		printf("internal error - lzo_init() failed !!!\n");
		printf("(this usually indicates a compiler bug - try recompiling\n"
		       "without optimizations, and enable '-DLZO_DEBUG' for diagnostics)\n");
		return 3;
	}

	fflush(stdout);
	parse_config.main_func(buf, fd, &parse_config);

	fflush(stdout);
	fclose(fd);

	parse_config.log("finished <%d>\n", api_id_list_length);
	return 0;
}
