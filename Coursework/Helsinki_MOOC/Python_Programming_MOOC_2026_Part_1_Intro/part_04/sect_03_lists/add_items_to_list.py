# Write your solution here

#make a programm that asks for a number of items then the value of each item and adds them to a list. Finally the program should print the list.
#no functions needed


limit = int(input("How many items do you want to add to the list? "))
counter = 0

item_list = []

while counter < limit :
    item_user = int(input("Enter the value of the item: "))
    item_list.append(item_user)
    counter += 1

print(item_list)
