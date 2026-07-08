# Write your solution here
####################################################################
def add_to_dict(dict_file_name: str, finnish: str, english: str):
    with open(dict_file_name, 'a') as file:
        file.write(finnish + ';' + english + '\n')
    print('Dictionary entry added')

def search_dict(dict_file_name: str, search_term: str):
    search_term = search_term.lower()
    with open(dict_file_name) as file:
        for line in file:
            line = line.replace('\n','')
            line = line.strip()
            parts = line.split(';')
            finnish = parts[0].lower()
            english = parts[1].lower()
            if search_term in finnish or search_term in english:
                print(f'{finnish} - {english}')

def main():
    dict_file_name = 'dictionary.txt'
    while True:
        print('1 - Add word, 2 - Search, 3 - Quit')
        choice = int(input('Function: '))
        if choice == 1:
            finnish = input('The word in Finnish: ')
            english = input('The word in English: ')
            add_to_dict(dict_file_name, finnish, english)
        elif choice == 2:
            search_term = input('Search term: ')
            search_dict(dict_file_name, search_term)
        elif choice == 3:
            print('Bye!')
            break

main()
######################################################################


#model solution
def read_dictionary():
    # Words are stored in a list. If the translation would always
    # be to same direction (e.g. from English to Finnish),
    # using dictionary as a data structure would be a good idea
    dictionary = []
 
    with open("dictionary.txt") as file:
        # In the example file, word pair is at one line as
        # finnish;english, for example
        # auto;car
        for row in file:
            row = row.replace("\n","")
            dictionary.append(tuple(row.split(";")))
 
    return dictionary
 
def add_word(dictionary: list):
    word_fi = input("The word in Finnish: ")
    word_en = input("The word in English: ")
    # Add to list
    dictionary.append((word_fi, word_en))
 
    # Write to file
    with open("dictionary.txt", "a") as file:
        file.write(word_fi + ";" + word_en + "\n")
        print("Dictionary entry added")
 
def search_word(dictionary: list):
    word = input("Search term: ")
    for word_fi, word_en in dictionary:
        if word in word_fi or word in word_en:
            print(f"{word_fi} - {word_en}")
 
 
dictionary = read_dictionary()
while True:
    print("1 - Add word, 2 - Search, 3 - Quit")
    function = input("Function: ")
    if function == "1":
        add_word(dictionary)
    elif function == "2":
        search_word(dictionary)
    elif function == "3":
        print("Bye!")
        break