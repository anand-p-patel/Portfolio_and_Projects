# Write your solution here

phone_book = {}
while True:
    user_input = int(input("command (1 search, 2 add, 3 quit)"))
    if user_input == 3:
        print("quitting...")
        break
    if user_input == 2:
        user_phone_name = str(input("name: "))
        user_phone_number = input("number:")
        if user_phone_name in phone_book:
            phone_book[user_phone_name].append(user_phone_number)
        else:
            phone_book[user_phone_name] = [user_phone_number]
        print("ok!")
    if user_input == 1:
        search_name = input("name: ")
        if search_name not in phone_book:
            print(f"no number")
            continue
        for number in phone_book[search_name]:
            print(number)