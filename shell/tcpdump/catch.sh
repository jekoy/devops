#!/bin/bash

# 文件存储路径
DIR="/data0/catch_files"

# 删除最旧的文件
delete_oldest() {
    # 获取最旧的文件，并删除
    oldest_file=$(ls -t "$DIR" | tail -n 1)
    rm -f "$DIR/$oldest_file"
}

# 抓包函数
capture_packets() {
    while :
    do
        # 创建新文件
        filename="$(date +'%Y_%m%d_%H%M_%S').pcap"
        tcpdump  -s0 -G 300 -W 1 -i eth1 host 10.110.1.202 -w "$DIR/$filename"
        # 删除最旧的文件，只保留最新的72个文件
        num_files=$(ls "$DIR" | wc -l)
        while [ "$num_files" -gt 72 ]; do
            delete_oldest
            num_files=$(ls "$DIR" | wc -l)
        done
    done
}

# 开始抓包
capture_packets