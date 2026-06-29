JJPARSER ?= /home/yan/repos/github/JJParser
CC ?= gcc
CFLAGS ?= -O2 -Wall -Wextra -Wno-format-overflow -I$(JJPARSER)
LDFLAGS ?= -lcurl -lm

JJPARSER_OBJS = \
	$(JJPARSER)/ListStatistics.o \
	$(JJPARSER)/List.o \
	$(JJPARSER)/Examine.o \
	$(JJPARSER)/Modify.o \
	$(JJPARSER)/Tree.o \
	$(JJPARSER)/TreeStatistics.o \
	$(JJPARSER)/ParseTPTP.o \
	$(JJPARSER)/ParseTSTP.o \
	$(JJPARSER)/PrintTSTP.o \
	$(JJPARSER)/Parsing.o \
	$(JJPARSER)/Signature.o \
	$(JJPARSER)/Tokenizer.o \
	$(JJPARSER)/Utilities.o \
	$(JJPARSER)/Compare.o \
	$(JJPARSER)/Interpret.o \
	$(JJPARSER)/PrintXML.o \
	$(JJPARSER)/PrintSMT2.o \
	$(JJPARSER)/PrintDFG.o \
	$(JJPARSER)/PrintOtter.o \
	$(JJPARSER)/PrintKIF.o \
	$(JJPARSER)/PrintSUMO.o \
	$(JJPARSER)/PrintLP.o \
	$(JJPARSER)/PrintDK.o \
	$(JJPARSER)/FileUtilities.o \
	$(JJPARSER)/SystemOnTPTP.o \
	$(JJPARSER)/Statistics.o

.PHONY: all clean jjparser

all: build/vizabelle-jjparser-json

jjparser:
	$(MAKE) -C $(JJPARSER)

build/vizabelle-jjparser-json: tools/jjparser_json.c $(JJPARSER_OBJS) | build
	$(CC) $(CFLAGS) -o $@ $< $(JJPARSER_OBJS) $(LDFLAGS)

build:
	mkdir -p build

clean:
	rm -rf build

