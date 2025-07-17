# devops


功能：
1.持续抓包
2.只保留最新的72个pcap文件
3.相当于一个文件的数据是5min抓的数据

启停：
mkdir -p  /data0/catch_files
nohup sh catch.sh >log_catch.out 2>&1 &
ps aux |grep catch|grep -v grep|awk '{print $2}'|xargs kill -9