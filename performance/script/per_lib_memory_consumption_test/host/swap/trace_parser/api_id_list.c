#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "api_id_list.h"

const char **api_id_list;
unsigned int api_id_list_length;

void init_api_id_list(const char *api_map_file_path)
{
	FILE *f = NULL;
	int n, res;
	int size;
	char line[1024];
	const char **list;
	api_id_list = NULL;

	api_id_list = NULL;
	api_id_list_length = 0;

	size = 0;
	list = malloc(size * sizeof(*list));
	if (api_map_file_path == NULL)
		goto exit;

	f = fopen(api_map_file_path, "r");
	if (f == NULL)
		goto exit;

	do {
		char *api_name = fgets(line, sizeof(line), f);
		if (api_name == NULL)
			break;
		res = sscanf(api_name, "%d", &n);
		api_name = strstr(api_name, " ");
		if (api_name == NULL)
			break;
		api_name++;
		api_name[strlen(api_name) - 1] = 0;

		if (res != 1 || api_name == NULL)
			break;
		if (n + 1 >= size) {
			list = realloc(list, (n + 1) * sizeof(*list));
			size = n + 1;
		}
		list[n] = strdup(api_name);
	} while (res != EOF);

	api_id_list = list;
	api_id_list_length = size;

exit:
	/* use buildin table */
	if (f != NULL)
		fclose(f);
}
