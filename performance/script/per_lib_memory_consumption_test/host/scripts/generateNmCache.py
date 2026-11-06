import sys
from sys import argv, exit
from os import unlink, path
import os.path
import re
import logging
import time
from subprocess import check_output, Popen, PIPE


probeCandidates = set()
symbols = 0
aul_status_updateAddress = None

def generateProbeCandidates(binaryPath, binaryIsLib = 1):
    global probeCandidates
    nameSearcher = re.compile(".* U (.*)")
    undefinedSymbol = re.compile(' U ')
    if binaryIsLib:
        out = check_output(["nm", "-D", binaryPath])
    else:
        out = check_output(["nm", binaryPath])

    out = out.decode().split('\n')
    for i in xrange(len(out)):
        if undefinedSymbol.search(out[i]):
            demangledName = nameSearcher.match(out[i]).group(1)
            probeCandidates.add(demangledName.strip())


def generateSymbolsList(binaryPath, binaryIsLib = True):
    global probeCandidates,symbols,aul_status_updateAddress
    if not path.exists(binaryPath):
        return []

    nmFile = []
    nameSearcher = re.compile(".* [tTW] (.*)")
    if binaryIsLib:
        out = check_output(["nm", "-D", binaryPath])
    else:
        out = check_output(["nm", binaryPath])

    out = out.decode().split('\n')
    for i in xrange(len(out)):
        result = nameSearcher.match(out[i])
        if result is not None:
            demangledName = result.group(1).strip()
            if demangledName in probeCandidates or not binaryIsLib:
                symbols += 1
                if "aul_status_update" in demangledName:
                    aul_status_updateAddress = int(out[i].split()[0], 16)

                nmFile.append(demangledName)

    return nmFile

def filterFunc(x):
    return "libpthread.so" not in x and "libdl.so" not in x

def getLibrariesList(binaryPath):
    logging.debug("Getting library list for %s" % binaryPath)
    out = check_output(["readelf", "-d", binaryPath])
    logging.debug("Readelf succeded")
    l = filter(filterFunc, map(lambda x: x.split()[4][1:-1], filter(lambda x: "Shared" in x, out.split('\n'))))
    logging.debug("Returning list:" + str(l))
    return l

def generateInstrumentationsConfig(app_id, appPath, memoryProfiling, cache_directory = "/tmp"):
    global aul_status_updateAddress
    aul_status_updateAddress = None
    numberOfSymbols = 0

    binaryPath = appPath
    binaryName = os.path.join(cache_directory, os.path.basename(binaryPath))

    fileText = """
APP_NATIVE =1
APP_RUNNING=2
APP_COMMON =3
APP_WEB    =4

app_inst_list = [
{
    "app_type":
        APP_RUNNING,

    "app_id":
        "",

    "app_path":
        "%s",

    "app_probes":
        [

""" % (binaryPath)

    if not memoryProfiling:
        logging.debug("Checking for " + os.path.join(cache_directory, binaryName) + " exists")
        if not os.path.exists(os.path.join(cache_directory, binaryName)):
            logging.debug("sdb pull " + binaryPath + " " + cache_directory)
            os.system("sdb pull " + binaryPath + " " + cache_directory)
            if not os.path.exists(os.path.join(cache_directory, binaryName)):
                logging.critical("Application %s does not installed!" % app_id)
                return None
        else:
            logging.debug(os.path.join(cache_directory, binaryName) + " exists")
        for symbol in generateSymbolsList(binaryName, binaryIsLib = False):
            numberOfSymbols += 1
            fileText += "            (\"%s\", 0, (\"\", \"p\")),\n" % symbol

        fileText = fileText[:-2] + "\n"


    fileText += """
        ],

    "kernel_probes":
        [
        ],

    "life_cycle_probes":
        [
            0x0000, #main address             |   int  |     8
            0x0000  #plt app_efl_main address |   int  |     8
        ]
}

]

lib_inst_list = [

{

"""
    if not memoryProfiling:
        libsDict = {}
        i = 0
        targetPath = ""
        libraries = getLibrariesList(binaryName)
        generateProbeCandidates(binaryName, binaryIsLib = 0)
    #    os.remove(binaryName)
        while i < len(libraries):
            lib = libraries[i]
            i += 1

            if not libsDict.has_key(lib):
                hostFullName = os.path.join(cache_directory, lib)
                logging.debug("Checking %s existance" % hostFullName)
                if not os.path.exists(hostFullName):
                    out = None
                    logging.debug("Pulling " + lib)
                    count = 0
                    while 1:
                        logging.debug("Searching for library %s at target" % lib)
                        out = check_output(["sdb", "shell", "find", "/lib", "/usr/lib", "-name", lib], stderr=None)
                        if not out:
                            out = check_output(["sdb", "shell", "find", "/", "-name", lib], stderr=None)
                        if out:
                            break
                        time.sleep(1)
                        count += 1
                        if count > 10:
                            logging.critical("Giving up after %d searching of lib %s" % (count, lib))
                            break

                    targetPath = out.decode().split('\n')[0].strip()
                    fullPathFp = open(hostFullName + ".path", "w" )
                    fullPathFp.write(targetPath)
                    fullPathFp.close()

                    count = 0
                    while 1:
                        logging.debug("sdb pull " + targetPath + " " + cache_directory)
                        retCode = os.system("sdb pull " + targetPath + " " + cache_directory)
                        if os.path.exists(hostFullName):
                            break
                        time.sleep(1)
                        count += 1
                        if count > 10:
                            logging.critical("Giving up after %d pulling of lib %s" % (count, lib))
                            break


                libsDict[lib] = ""
                logging.debug("Processing " + lib)
                generateProbeCandidates(hostFullName)
                libraries += getLibrariesList(hostFullName)

        libraries = list(set(libraries))
        i = 0
        while i < len(libraries):
            lib = libraries[i]
            i += 1
            hostFullName = os.path.join(cache_directory, lib)
            for symbol in generateSymbolsList(hostFullName):
                numberOfSymbols += 1
                libsDict[lib] += "        (\"%s\", 0, (\"\", \"p\")),\n" % symbol

            if path.exists(cache_directory + lib):
                libsDict[lib] = libsDict[lib][:-2] + "\n"
    #            os.remove(lib)


        for lib in libsDict.keys():
            hostFullName = os.path.join(cache_directory, lib)
            fullPathFp = open(hostFullName + ".path", "r" )
            targetPath = fullPathFp.read()
            fullPathFp.close()

            fileText += "    \"%s\": [\n" % targetPath
            fileText += libsDict[lib]
            fileText += "],\n"


        fileText = fileText[:-2] + "\n"
    fileText += """
}

]
"""
    logging.debug("Generated %d symbols" % numberOfSymbols)
    return fileText

def main():
    if len(sys.argv) != 2:
        print "Usage: ./%s <applicationID>" % sys.argv[0]
    print generateInstrumentationsConfig(sys.argv[1])

if __name__ == "__main__":
    main()

