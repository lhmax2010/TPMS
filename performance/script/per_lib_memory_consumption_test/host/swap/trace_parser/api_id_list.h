#ifndef __API_ID_LIST_H__
#define __API_ID_LIST_H__

#include "ctype.h"

const char **api_id_list;
void init_api_id_list(const char *api_map_file_path);
unsigned int api_id_list_length;

#endif /* __API_ID_LIST_H__ */
