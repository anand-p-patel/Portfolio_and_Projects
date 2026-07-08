# Write your solution here
def read_file(filename):
    with open(filename) as file:
        content= []
        for line in file:
            line = line.replace('\n','')
            line = line.split(';')
            content.append(line)
        return content

def evaluate_data(content, correct_filename, incorrect_filename):
    open(correct_filename, 'w').close()
    open(incorrect_filename, 'w').close()
    correct_file = open(correct_filename, 'w')
    incorrect_file = open(incorrect_filename, 'w')
    for solution in content:
        sol = ';'.join(solution)
        sol += '\n'
        if eval(solution[1]) == int(solution[2]):
            correct_file.write(sol)
        else:
            incorrect_file.write(sol)
    correct_file.close()
    incorrect_file.close()

def filter_solutions():
    content = read_file('solutions.csv')
    evaluate_data(content, 'correct.csv', 'incorrect.csv')
