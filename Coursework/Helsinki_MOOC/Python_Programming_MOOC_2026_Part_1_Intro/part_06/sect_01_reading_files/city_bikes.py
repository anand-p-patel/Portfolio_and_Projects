# Write your solution here

import math

def read_file(filename):
    with open(filename) as file:
        lines = []
        for line in file:
            line = line.replace('\n', '')
            line = line.strip()
            if 'longitude' in line.lower():
                continue
            lines.append(line)
        return lines

def get_station_data(filename):
    stations_raw = read_file(filename)
    stations = {}
    for station in stations_raw:
        station_data = station.split(';')
        name = station_data[3]
        long = float(station_data[0])
        lat = float(station_data[1])
        stations[name] = (long, lat)
    return stations

def distance(stations, station1, station2):
    long1, lat1 = stations[station1]
    long2, lat2 = stations[station2]

    x_km = (long1 - long2) * 55.26
    y_km = (lat1 - lat2) * 111.2
    distance_km = math.sqrt(x_km**2 + y_km**2)
    return distance_km

def greatest_distance_from_one_station(stations, stations_list, station):
    start = stations_list.index(station)+1
    compare_list = stations_list[start:]
    greatest_tuple = None
    greatest = 0
    for compare in compare_list:
        d = distance(stations, station, compare)
        if d > greatest:
            greatest_tuple = (station, compare, d)
            greatest = d
    return greatest_tuple


def greatest_distance(stations):
    stations_list = []
    for key, value in stations.items():
        stations_list.append(key)

    greatest_tuple = None
    greatest = 0
    for index, station in enumerate(stations_list):
        if index < len(stations_list)-1:
            stations_distance = greatest_distance_from_one_station(stations,stations_list,station)
            station1, station2, distance = stations_distance
            if distance > greatest:
                greatest_tuple = stations_distance
                greatest = distance
    return greatest_tuple