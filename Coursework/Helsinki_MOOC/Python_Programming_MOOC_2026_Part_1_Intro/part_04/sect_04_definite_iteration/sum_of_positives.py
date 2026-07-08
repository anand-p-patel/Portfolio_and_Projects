# Write your solution here


def sum_of_positives(my_list):
    count = 0
    positive_array = []
    while count < len(my_list):
        if my_list[count] > 0:
            positive_array.append(my_list[count])
        count += 1
    result = sum(positive_array)
    return result


if __name__ == "__main__":
    my_list = [1,2,3,4,5]
    result = sum_of_positives(my_list)
    print("The result is", result)


    #def sum_of_positives(my_list) :
    #count = 0
   # positive_array = []
    #while count < len(my_list) :
        #if my_list[count] > 0:
            #current_value = my_list[count]
           # positive_array.append(current_value)
            #count += 1 moved out of loop, was the issue
    #result = sum(positive_array)
   # return result