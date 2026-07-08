# Write your solution here

#user string
row = "-"

while True :
    user_string = str(input("Please type in a string:"))
    if user_string == "" :
        break
    else:
        print(user_string)
        print(row * len(user_string))