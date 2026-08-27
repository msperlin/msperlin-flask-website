#! /bin/bash 

my_path='/home/msperlin/Desktop/output'
mkdir $my_path

docker run -v "$my_path":/home/msperlin/output example_docker 