
TARGET = trace_parser

SRC_C = \
	protocol_v3_0.c \
	protocol_v4_0.c \
	protocol_v4_1.c \
	protocol_v4_2.c \
	api_id_list.c \
	trace_parser.c \
	trace_parser_text.c \
	trace_parser_json.c \
	trace_parser_py.c \
	trace_parser_uihv.c \
	trace_parser_mongo.c \
	minilzo.c

SRC_CXX = \
	library_map.cpp

OBJS := $(SRC_C:.c=.o) $(SRC_CXX:.cpp=.o)

WARN_CFLAGS = 					\
		-Wall					\
		-funwind-tables			\
		-fomit-frame-pointer	\
		-Xlinker				\
		--no-undefined			\
		-Werror					\
		-Wextra					\
		-O0						\
		-Wwrite-strings			\
		-Wlogical-op			\
		-Wpacked				\
		-Winline				\
		-Wno-psabi

INC_CFLAGS = -I.
CFLAGS = $(WARN_CFLAGS) $(INC_CFLAGS) $(LD_CFLAGS) -fPIC

%.o : %.c
	$(CC) -c $(CFLAGS) $< -o $@

%.o : %.cpp
	$(CXX) -c $(CXXFLAGS) $< -o $@


all: clean $(TARGET)

mongo: CFLAGS+=-DMONGO_HAVE_STDINT -DMONGO_ENABLE
mongo: LDFLAGS+=-lmongoc
mongo: clean $(TARGET)

msgnames: CFLAGS+=-DMSG_WITH_NAMES
msgnames: clean $(TARGET)

$(TARGET): $(OBJS)
	$(CXX) $^ -o $@

clean:
	rm -f $(OBJS)
	rm -f $(TARGET)
