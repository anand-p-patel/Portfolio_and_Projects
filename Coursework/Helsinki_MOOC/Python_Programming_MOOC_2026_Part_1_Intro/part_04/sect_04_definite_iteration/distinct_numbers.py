# Write your solution here
def distinct_numbers(my_list):
    distinct = []
    repeat = []
    for number in my_list:
        if number in distinct:
            repeat.append(number)
        else:
            distinct.append(number)
    distinct_sorted = sorted(distinct)
    return distinct_sorted

if __name__ == "__main__":
    my_list = [3, 2, 2, 1, 3, 3, 1]
    print(distinct_numbers(my_list)) # [1, 2, 3]



#elegant model solution
#def distinct_numbers(my_list: list):
#    results = []
#    for item in my_list:
#        if item not in results:
#            results.append(item)
# 
#    results.sort()
#    return results
