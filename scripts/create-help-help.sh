#!/usr/bin/env bash
PATH=".:jami_commander/:$PATH" &&
    jc --help >help.help.txt
echo "help.help.txt is $(wc -l help.help.txt | cut -d ' ' -f1) lines long"
