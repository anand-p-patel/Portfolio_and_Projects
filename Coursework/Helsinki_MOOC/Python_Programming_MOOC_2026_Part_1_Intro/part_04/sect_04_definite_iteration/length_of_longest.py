# Write your solution here

#my_list = ["larry", "curly", "moe", "abdullah"]
#print(len(my_list[3]))

def length_of_longest(my_list):
    longest = 0
    for word in my_list :
        if len(word) > longest:
            longest = len(word)
    result = longest
    return longest

if __name__ == "__main__":
    my_list = ["first", "second", "fourth", "eleventh"]
    result = length_of_longest(my_list)
    print(result)