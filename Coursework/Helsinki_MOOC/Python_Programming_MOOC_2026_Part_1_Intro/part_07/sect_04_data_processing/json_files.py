# Write your solution here
import json


def print_persons(filename):
    with open(filename) as my_file:
        data = my_file.read()
        persons = json.loads(data)
        for person in persons:
            name = person["name"]
            age = str(person["age"]) + " years"
            hobbies = "(" + ", ".join(person["hobbies"]) + ")"
            print(f"{name} {age} {hobbies}")
