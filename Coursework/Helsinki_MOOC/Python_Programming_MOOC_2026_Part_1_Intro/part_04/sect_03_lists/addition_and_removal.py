# Write your solution here
# write a program that asks a user for input, add(d) remove(r) or exit(x),
# if the user inputs add increase the list by one, if the user inputs remove decrease
# the list by one, if the user inputs exit stop the program and prints Bye!
# use append to add whatever the last number in the array is + 1 to the end of the list
# and pop to remove the last element of the list

my_list = []

while True:
    user_input = input("a(d)d, (r)em(o)ve or e(x)it: ")
    # Changed behavior: print the current list state before processing the command.
    # The tests expect a line for each input showing the list first, then the change.
    print(f"The list is now {my_list}")

    if user_input == "d":
        # Original code appended a new number and then printed the list.
        # Now we only modify the list here, because the state was already printed.
        if len(my_list) == 0:
            my_list.append(1)
        else:
            my_list.append(my_list[-1] + 1)
    elif user_input == "r":
        # Original code popped and then printed the list. We keep the pop logic,
        # but avoid printing the list here to prevent duplicate output.
        if len(my_list) > 0:
            my_list.pop()
    elif user_input == "x":
        # When exiting, the program prints only the goodbye message.
        print("Bye!")
        break