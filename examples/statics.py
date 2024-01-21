import tokenize

def count_lines_classes_functions(filename):
    # 统计行数
    lines = 0
    classes = 0
    functions = 0

    with open(filename, 'rb') as f:
        for _ in f:
            lines += 1
        f.seek(0)  # 重置文件指针到文件开头

        tokens = tokenize.tokenize(f.readline)
        for tok in tokens:
            if tok.type == tokenize.NAME and tok.string in ('class', 'def'):
                if tok.string == 'class':
                    classes += 1
                elif tok.string == 'def':
                    functions += 1

    return lines, classes, functions


if __name__ == '__main__':
    import os
    import glob

    path = 'D:\workspace\sourcecode\MetaGPT\metagpt'
    # 查找所有以.py结尾的文件
    py_files = glob.glob(os.path.join(path, '**\**.py'), recursive=True)

    statics = {}
    total_lines = 0
    total_classes = 0
    total_functions = 0
    # 输出文件名
    for file in py_files:
        print(file)
        lines, classes, functions = count_lines_classes_functions(file)
        total_lines += lines
        total_classes += classes
        total_functions += functions
        statics[file] = {'lines': lines, 'classes': classes, 'functions': functions}
    for k, v in statics.items():
        print(k, v)
    print(f'总行数: {total_lines}',f'类数量: {total_classes}',f'函数数量: {total_functions}')