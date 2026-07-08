# Write your solution here
def new_person(name, age):
    if name == "" or len(name.split(" ")) < 2 or len(name) > 40 or age < 0 or age > 150:
        raise ValueError("Check parameters again")
    return(name, age)