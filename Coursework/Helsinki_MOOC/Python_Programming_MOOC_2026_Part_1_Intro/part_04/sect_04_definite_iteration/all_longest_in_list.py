# Write your solution here
# Write your solution here
# Write your solution here

#my_list = ["larry", "curly", "moe", "abdullah"]
#print(len(my_list[3]))

def all_the_longest(my_list):
    max_length = 0
    for word in my_list:
        if len(word) > max_length:
            max_length = len(word)

    longest = []
    for word in my_list :
        if len(word) == max_length :
            longest.append(word)
    result = longest
    return result

if __name__ == "__main__":
    my_list = ["adele", "mark", "dorothy", "tim", "hedy", "richard"]
    result = all_the_longest(my_list)
    print(result) # ['dorothy', 'richard']