#!/usr/bin/env bash
PATH=".:jami_commander/:$PATH" &&
    jc --usage >help.usage.txt
echo "help.usage.txt is $(wc -l help.usage.txt | cut -d ' ' -f1) lines long"
