def find_words(search_term):
    results = []
    
    with open("words.txt") as file:
        stripped_words = search_term.replace("*", "")

        for word in file:
            word = word.replace("\n", "")
            if "*" in search_term:
                if search_term[0] == "*":
                    if word.endswith(stripped_words):
                        results.append(word)
            elif "." in search_term:
                if len(search_term) == len(word):
                    match = True
                    for i in range(len(search_term)):
                        if search_term[i] != "." and search_term[i] != word[i]:
                            match = False
                            break
                    if match:
                        results.append(word)
            else:
                if word == search_term:
                    results.append(word)
        return results