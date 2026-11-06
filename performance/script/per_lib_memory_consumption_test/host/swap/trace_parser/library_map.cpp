#include <map>
#include <list>
#include <string>
#include <errno.h>
#include <stdint.h>
#include "library_map.h"


class Mapping
{
public:
    Mapping(uint64_t lowAddr, uint64_t highAddr, const char *path) :
        lowAddr_(lowAddr), highAddr_(highAddr), path_(path)
    {}

    void setLowAddr(uint64_t addr) { lowAddr_ = addr; }
    void setHighAddr(uint64_t addr) { highAddr_ = addr; }

    const char *name() { return path_.c_str(); }
    uint64_t lowAddr() { return lowAddr_; }
    uint64_t highAddr() { return highAddr_; }

    void addSpace(const Mapping *map)
    {
        addSpace(map->lowAddr_, map->highAddr_);
    }

    void addSpace(uint64_t lowAddr, uint64_t highAddr)
    {
        lowAddr_ = std::min(lowAddr_, lowAddr);
        highAddr_ = std::max(highAddr_, highAddr);
    }

    bool isInRange(uint64_t lowAddr, uint64_t highAddr)
    {
        return lowAddr <= lowAddr_ && highAddr_ <= highAddr;
    }

    bool isInMap(uint64_t addr)
    {
        return lowAddr_ <= addr && addr < highAddr_;
    }

    bool intersection(uint64_t lowAddr, uint64_t highAddr)
    {
        intersection(lowAddr_, highAddr_, lowAddr, highAddr);
    }

    bool intersection(const Mapping *m)
    {
        return intersection(this, m);
    }

    static bool intersection(uint64_t l1, uint64_t h1, uint64_t l2, uint64_t h2)
    {
        return (l2 <= l1 && l1 < h2) || (l2 < h1 && h1 <= h2);
    }

    static bool intersection(const Mapping *m1, const Mapping *m2)
    {
        return intersection(m1->lowAddr_, m1->highAddr_, m2->lowAddr_, m2->highAddr_);
    }

private:
    uint64_t lowAddr_;
    uint64_t highAddr_;
    std::string path_;
};


class App
{
public:
    App(uint32_t pid) : pid_(pid) {}
    ~App()
    {
        for (MappingList::const_iterator it = mapList_.begin(),
             itEnd = mapList_.end(); it != itEnd; ++it)
            delete *it;
    }

    int memoryMap(uint64_t lowAddr, uint64_t highAddr, const char *path)
    {
        if (lowAddr >= highAddr)
            return -EINVAL;

        Mapping *map = new Mapping(lowAddr, highAddr, path);

        if (mapList_.empty()) {
            mapList_.push_back(map);
            return 0;
        }

        if ((*mapList_.begin())->lowAddr() >= highAddr) {
            mapList_.push_front(map);
            return 0;
        }

        bool find = false;
        MappingList::iterator it = mapList_.begin();
        while (it != mapList_.end()) {
            const Mapping *m = *it;
            if (Mapping::intersection(map, m)) {
                find = true;
                map->addSpace(m);
                it = mapList_.erase(it);
                delete m;
            } else {
                if (find)
                    break;
                ++it;
            }
        }

        if (find)
            mapList_.insert(--it, map);
        else
            mapList_.push_back(map);

        return 0;
    }

    int memoryUnmap(uint64_t lowAddr, uint64_t highAddr)
    {
        if (lowAddr >= highAddr)
            return -EINVAL;

        bool find = false;
        MappingList::iterator it = mapList_.begin();
        while (it != mapList_.end()) {
            Mapping *m = *it;
            if (m->intersection(lowAddr, highAddr)) {
                find = true;
                if (m->isInRange(lowAddr, highAddr)) {
                    lowAddr = m->highAddr();
                    it = mapList_.erase(it);
                    delete m;
                    continue;   // erase returns next element
                } else if (m->isInMap(lowAddr)) {
                    m->setHighAddr(lowAddr);
                } else if (m->isInMap(highAddr)) {
                    m->setLowAddr(highAddr);
                }
            } else {
                if (find)
                    break;
            }
            ++it;
        }

        return 0;
    }

    Mapping *map(uint64_t addr)
    {
        static Mapping *map = 0;    // optimization

        if (map && map->isInMap(addr))
            return map;

        for (MappingList::const_iterator it = mapList_.begin(),
             itEnd = mapList_.end(); it != itEnd; ++it) {
            map = *it;
            if (map->isInMap(addr))
                return map;
        }

        return 0;
    }

    uint32_t pid() { return pid_; }

private:
    typedef std::list<Mapping *> MappingList;

    uint32_t pid_;
    MappingList mapList_;
};


typedef std::list<App *> AppList;
static AppList appList;

static App *getApp(uint32_t pid)
{
    static App *app = 0;    // optimization

    if (app && app->pid() == pid)
        return app;

    for (AppList::const_iterator it = appList.begin(),
         itEnd = appList.end(); it != itEnd; ++it) {
        app = *it;

        if (app->pid() == pid)
            return app;
    }

    return 0;
}

extern "C" int lmap_app_add(uint32_t pid)
{
    if (getApp(pid))
        return -EBUSY;

    appList.push_back(new App(pid));
    return 0;
}

extern "C" int lmap_app_del(uint32_t pid)
{
    for (AppList::iterator it = appList.begin(),
         itEnd = appList.end(); it != itEnd; ++it) {
        if ((*it)->pid() == pid) {
            appList.erase(it);
            return 0;
        }
    }

    return -ESRCH;
}

extern "C" int lmap_mmap(uint32_t pid, uint64_t low_add, uint64_t high_addr,
                         const char *binary_path)
{
    App *app = getApp(pid);
    if (!app)
        return -ESRCH;

    return app->memoryMap(low_add, high_addr, binary_path);
}

extern "C" int lmap_unmap(uint32_t pid, uint64_t low_add, uint64_t high_addr)
{
    App *app = getApp(pid);
    if (!app)
        return -ESRCH;

    return app->memoryUnmap(low_add, high_addr);
}

extern "C" bool lmap_map_info(uint32_t pid, uint64_t addr, struct lmap_info *info)
{
    Mapping *m = getApp(pid)->map(addr);
    if (!m)
        return false;

    info->name = m->name();
    info->offset = addr - m->lowAddr();

    return true;
}
