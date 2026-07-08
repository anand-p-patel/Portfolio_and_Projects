# Write your solution here

def read_file(filename):
    file_lines = []
    with open(filename) as file:
        for line in file:
            line = line.replace('\n', '')
            file_lines.append(line)
    return file_lines
    
def recipe_list_from_file(filename):
    recipe_list = []
    file_lines = read_file(filename)
    tot_recipe_list = file_lines.count('') + 1
    start = 0
    for i in range(tot_recipe_list):
        recipe_dict = {}
        recipe_dict['name'] = file_lines[start]
        recipe_dict['prep time'] = file_lines[start+1]
        try:
            end_index = file_lines.index('', start)
        except:
            end_index = len(file_lines)
        recipe_dict['ingredients'] = file_lines[start+2:end_index]
        start = end_index + 1
        recipe_list.append(recipe_dict)
    return recipe_list

def search_by_name(filename, word):
    recipes = recipe_list_from_file(filename)
    found_recipes = []
    for i in range(len(recipes)):
        name = recipes[i]['name']
        if word.lower() in name.lower():
            found_recipes.append(name)
    return found_recipes


def search_by_time(filename, prep_time):
    recipes = recipe_list_from_file(filename)
    found_recipes = []
    for i in range(len(recipes)):
        time = int(recipes[i]['prep time'])
        if time < prep_time:
            recipe = recipes[i]['name'] + ', preparation time ' + str(time) + ' min'
            found_recipes.append(recipe)
    return found_recipes

def search_by_ingredient(filename, ingredient):
    recipes = recipe_list_from_file(filename)
    found_recipes = []
    for i in range(len(recipes)):
        for ingr in recipes[i]['ingredients']:
            if ingr == ingredient:
                time = int(recipes[i]['prep time'])
                recipe = recipes[i]['name'] + ', preparation time ' + str(time) + ' min'
                found_recipes.append(recipe)
    return found_recipes