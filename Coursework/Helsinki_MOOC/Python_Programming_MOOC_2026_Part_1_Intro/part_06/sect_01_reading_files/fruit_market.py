# write your solution here

def read_fruits():
    fruit_dict = {}
    with open("fruits.csv", "r") as file:
        for line in file:
            line = line.replace("\n", "")
            parts = line.split(";")
            fruit_dict[parts[0]] = float(parts[1])
    return fruit_dict