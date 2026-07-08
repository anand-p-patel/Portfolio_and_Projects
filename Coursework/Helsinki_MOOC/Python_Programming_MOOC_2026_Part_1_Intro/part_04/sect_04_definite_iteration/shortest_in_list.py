# Write your solution here
# Write your solution here

#my_list = ["larry", "curly", "moe", "abdullah"]
#print(len(my_list[3]))

def shortest(my_list):
    shortest = my_list[0]
    for word in my_list :
        if len(word) < len(shortest) :
            shortest = word
    result = shortest
    return result

if __name__ == "__main__":
    my_list = ["first", "second", "fourth", "eleventh"]
    result = shortest(my_list)
    print(result)