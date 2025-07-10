"""
Modified code from IP2Trace library.
"""
from typing import Generator
from random import choices
from re import match
import IP2Location
import platform
import socket
import struct
import select
import time
import sys
import os

ICMP_ECHO = 8
ICMP_V6_ECHO = 128
ICMP_ECHO_REPLY = 0
ICMP_V6_ECHO_REPLY = 129
ICMP_TIME_EXCEEDED = 11
MIN_SLEEP = 100

if platform.system() == 'Windows':
    socket.IPPROTO_IPV6 = 41
    socket.IPPROTO_ICMPV6 = 58


def calculate_checksum(packet):
    countTo = (len(packet) // 2) * 2
    count = 0
    sum = 0
    while count < countTo:
        if sys.byteorder == "little":
            loByte = packet[count]
            hiByte = packet[count + 1]
        else:
            loByte = packet[count + 1]
            hiByte = packet[count]
        sum = sum + (hiByte * 256 + loByte)
        count += 2
    if countTo < len(packet):
        sum += packet[count]
    sum = (sum >> 16) + (sum & 0xffff)
    sum += (sum >> 16)
    answer = ~sum & 0xffff
    answer = socket.htons(answer)
    return answer

def is_ipv4(hostname) -> bool:
    pattern = r'^([0-9]{1,3}[.]){3}[0-9]{1,3}$'
    return match(pattern, hostname) is not None

def is_ipv6(hostname) -> bool:
    return ':' in hostname

def is_valid_ip(hostname) -> bool:
    return is_ipv4(hostname) or is_ipv6(hostname)

def to_ip(hostname):
    if is_valid_ip(hostname):
        return hostname
    return socket.gethostbyname(hostname)

def ip_to_domain_name(hostname):
    if is_valid_ip(hostname):
        try:
            return socket.gethostbyaddr(hostname)
        except socket.herror:
            return None
    return None



class RouteTracer:
    def __init__(self, destination_server: str):
        self.destination_server = destination_server
        self.identifier = os.getpid() & 0xffff
        self.seq_no = 0
        self.family = None

        self.packet_size = 80
        self.timeout = 500
        self.ttl = 1

        self.destination_ip = to_ip(destination_server)
        self.destination_domain_name = ip_to_domain_name(destination_server)
        self.ip2loc_db = IP2Location.IP2Location("tracing/IP2LOCATION-LITE-DB5.IPV6.BIN")

    def header_to_dict(self, keys, packet, struct_format):
        values = struct.unpack(struct_format, packet)
        return dict(zip(keys, values))

    def trace_route(self) -> Generator[tuple[int, str, str, str] | None]:
        icmp_header = None
        
        while self.ttl <= 30:
            self.seq_no = 0
            
            try:
                icmp_header, trace_data = self.tracer()
                if trace_data:
                    print(f"Got response: {trace_data}")
                    yield trace_data
            except socket.error:
                return None
                    
            self.ttl += 1

            if icmp_header is not None:
                if is_ipv4(self.destination_ip) and icmp_header['type'] == ICMP_ECHO_REPLY:
                    break
                
                elif is_ipv6(self.destination_ip) and icmp_header['type'] == ICMP_V6_ECHO_REPLY:
                    break

    def tracer(self) -> tuple | None:
        self.seq_no += 1

        if is_ipv4(self.destination_ip):
            self.family = socket.AF_INET
            icmp_socket = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
            icmp_socket.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, self.ttl)

        elif is_ipv6(self.destination_ip):
            self.family = socket.AF_INET6
            icmp_socket = socket.socket(socket.AF_INET6, socket.SOCK_RAW, socket.IPPROTO_ICMPV6)
            icmp_socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_UNICAST_HOPS, self.ttl)
            if platform.system() == 'Linux':
                icmp_socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_TCLASS, 0)

        sent_time = self.send_icmp_echo(icmp_socket)
        if sent_time is None:
            return None, None
        
        receive_time, icmp_header, ip_header = self.receive_icmp_reply(icmp_socket)
        icmp_socket.close()
        if receive_time:
            delay = (receive_time - sent_time) * 1000.0

        if ip_header is None:
            return None, None

        ip = socket.inet_ntoa(struct.pack('!I', ip_header['Source_IP']))
        try:
            sender_hostname = socket.gethostbyaddr(ip)[0]
        except socket.herror:
            sender_hostname = None
        
        iploc_data = self.ip2loc_db.get_all(ip)
        trace_data = {
            "ip": ip,
            "host": sender_hostname,
            "lat": float(iploc_data.latitude),
            "lon": float(iploc_data.longitude)
        }
            
        return (icmp_header, trace_data)

    def random_byte_message(self, size):
        sequence = choices(
            b'abcdefghijklmnopqrstuvwxyz'
            b'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
            b'1234567890', k=size)
        return bytearray(sequence)

    def send_icmp_echo(self, icmp_socket):
        start_value = 65
        payload = []
        
        if is_ipv4(self.destination_ip):
            header = struct.pack("!BBHHH", ICMP_ECHO, 0, 0, self.identifier, self.seq_no)
            for i in range(start_value, start_value+self.packet_size):
                payload.append(i & 0xff)
            data = bytearray(payload)
            
        elif is_ipv6(self.destination_ip):
            header = struct.pack("!BBHHH", ICMP_V6_ECHO, 0, 0, self.identifier, self.seq_no)
            data = self.random_byte_message(56)
            
        checksum = calculate_checksum(header + data)

        if is_ipv4(self.destination_ip):
            header = struct.pack("!BBHHH", ICMP_ECHO, 0, checksum, self.identifier, self.seq_no)
        elif is_ipv6(self.destination_ip):
            header = struct.pack("!BBHHH", ICMP_V6_ECHO, 0, checksum, self.identifier, self.seq_no)
            
        packet = header + data
        send_time = time.time()
        
        try:
            icmp_socket.sendto(packet, ((socket.getaddrinfo(host=self.destination_ip,port=None,family=self.family,type=socket.SOCK_RAW)[0][4])))
        except socket.error as err:
            return icmp_socket.close()
        return send_time

    def receive_icmp_reply(self, icmp_socket):
        timeout = self.timeout / 1000 
        time_limit = time.time() + timeout
        icmp_socket.settimeout(timeout)
    
        while True:
            remaining_time = time_limit - time.time()
            if remaining_time <= 0:
                return None, None, None
    
            ready = select.select([icmp_socket], [], [], remaining_time)
            receive_time = time.time()
    
            if not ready[0]:
                return None, None, None
    
            try:
                packet_data, _ = icmp_socket.recvfrom(1024)
            except socket.timeout:
                return None, None, None
    
            # Parse headers
            icmp_keys = ['type', 'code', 'checksum', 'identifier', 'sequence number']
            icmp_header = self.header_to_dict(icmp_keys, packet_data[20:28], "!BBHHH")
    
            ip_keys = ['VersionIHL', 'Type_of_Service', 'Total_Length', 'Identification', 'Flags_FragOffset', 'TTL', 'Protocol', 'Header_Checksum', 'Source_IP', 'Destination_IP']
            ip_header = self.header_to_dict(ip_keys, packet_data[:20], "!BBHHHBBHII")
    
            return receive_time, icmp_header, ip_header
    
