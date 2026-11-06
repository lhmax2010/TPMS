#ifndef LIBRARY_MAP_H
#define LIBRARY_MAP_H


#ifdef __cplusplus
extern "C" {
#endif

#include <stdint.h>
#include <stdbool.h>

struct lmap_info {
    const char *name;
    uint64_t offset;
};

int lmap_app_add(uint32_t pid);
int lmap_app_del(uint32_t pid);
int lmap_mmap(uint32_t pid, uint64_t low_add, uint64_t high_addr,
              const char *binary_path);
int lmap_unmap(uint32_t pid, uint64_t low_add, uint64_t high_addr);
bool lmap_map_info(uint32_t pid, uint64_t addr, struct lmap_info *info);


#ifdef __cplusplus
}
#endif


#endif // LIBRARY_MAP_H
