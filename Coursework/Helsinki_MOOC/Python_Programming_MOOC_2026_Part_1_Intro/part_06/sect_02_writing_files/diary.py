# Write your solution here
def read_file(file_name):
    with open(file_name) as diary:
        print("Entries:")
        for line in diary:
            print(line.replace("\n",''))

def update_file(file_name, entry):
    with open(file_name, 'a') as diary:
        diary.write(entry + "\n")





while True:
    print("1 - add an entry, 2 - read entries, 0 - exit")
    user_choice = int(input("Function:"))
    if user_choice == 1:
        #append dictionary
        entry = input("Diary entry: ")
        update_file("diary.txt", entry)
        print("Diary Saved")
    elif user_choice == 2:
        #display diary
        read_file("diary.txt")
    elif user_choice == 0:
        print("Bye now!")
        break