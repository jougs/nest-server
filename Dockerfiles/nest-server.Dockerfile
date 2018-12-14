FROM ubuntu:18.04

LABEL maintainer="Sebastian Spreizer <spreizer@web.de>"

RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    cython3 \
    libgsl0-dev \
    libltdl7-dev \
    libncurses5-dev \
    libreadline6-dev \
    python3-all-dev \
    python3-pip \
    python3-numpy \
    wget && \
    pip3 install flask==0.12.4 flask-cors

WORKDIR /tmp
RUN wget https://github.com/nest/nest-simulator/archive/v2.16.0.tar.gz && \
    tar zxf v2.16.0.tar.gz && \
    mkdir /tmp/nest-build

WORKDIR /tmp/nest-build
RUN cmake -DCMAKE_INSTALL_PREFIX:PATH=/opt/nest/ -Dwith-python=3 /tmp/nest-simulator-2.16.0 && \
    make && \
    make install && \
    rm -rf /tmp/*

COPY . /opt/nest-server
WORKDIR /opt/nest-server

EXPOSE 5000
RUN chmod 755 entrypoint.sh
ENTRYPOINT ["bash entrypoint.sh /opt/nest"]
