# Write your solution here

# ask user for editor choice
editor_choice = input("Editor: ")
lower_editor_choice = editor_choice.lower()

while lower_editor_choice != "visual studio code":
    if lower_editor_choice == "word" or lower_editor_choice == "notepad":
        print("awful")
    else:
        print("not good")

    editor_choice = input("Editor: ")
    lower_editor_choice = editor_choice.lower()

print("an excellent choice!")
#if editor_choice == "Visual Studio Code":
    #print("an excellent choice!")
    #if editor_choice == "Word" or editor_choice == "Notepad":
        #print("awful")
    #else:
        #print("not good")

#check for lower case input
#if lower_editor_choice == "visual studio code":
    #print("an excellent choice!")
    #if lower_editor_choice == "word" or lower_editor_choice == "notepad":
        #print("awful")
    #else:
        #print("not good")