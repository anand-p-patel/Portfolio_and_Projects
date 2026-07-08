#the goal is to write a program with a looping user input, the program will exit when the user types 0, other inputs will be added to a list, a second list will be created that orders the list from smallest to greatest
#no functions should be used
#start
#list_user_input = []
#create a second list to hold the sorted values
#list_ordered = []
#loop to get user input
#while True:
 #   user_input = input("Enter a number (or 0 to exit): ")
  #  if user_input == "0":
   #     break
    #else:
     #   list_user_input.append(int(user_input))

#sort the list from smallest to greatest using only basic while, if, else
#while list_user_input:
 #   smallest = list_user_input[0]
  #  for number in list_user_input:
   #     if number < smallest:
    #        smallest = number
    #list_ordered.append(smallest)
    #list_user_input.remove(smallest)

original = []

while True:
    user_input = input("New item: ")
    if user_input == "0":
        print("Bye!")
        break

    original.append(int(user_input))

    work = []
    i = 0
    while i < len(original):
        work.append(original[i])
        i += 1

    ordered = []
    while len(work) > 0:
        smallest = work[0]
        j = 1
        while j < len(work):
            if work[j] < smallest:
                smallest = work[j]
            j += 1

        ordered.append(smallest)

        k = 0
        while k < len(work):
            if work[k] == smallest:
                work.pop(k)
                break
            k += 1

    print("The list now:", original)
    print("The list in order:", ordered)