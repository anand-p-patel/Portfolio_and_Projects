# Write your solution here
#intialise a list with value of [ 1, 2, 3, 4, 5]
#ask user for index and new value
#change the value of the item at the given index to the new value
#program should loop until the user enters -1 as the index
# To change the value of an item in a list, you can use the index of the item and assign a new value to it. For example, if you have a list called "my_list" and you want to change the value of the item at index 2 to 10, you can do it like this: my_list[2] = 10. This will replace the old value at index 2 with the new value of 10.

index = 0
my_list = [1, 2, 3, 4, 5]
while index != -1:
    index = int(input("Index: "))
    if index == -1:
        break
    new_value = int(input("New value: "))
    if 0 <= index < len(my_list):
        my_list[index] = new_value
    print(my_list)