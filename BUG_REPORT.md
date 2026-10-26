# Reporting a Bug in OpenNovella

Thank you for helping make OpenNovella better! A good bug report gets fixed much faster.
You don't need to be a programmer to write one. Just tell us what happened.

---

## 1. Check that it's really a bug

- **Update first.** The problem may already be fixed in the latest version.
- **Run Check Story (F7)** in the editor. Many "bugs" are a broken link, a missing image, or a
  condition with a typo, and Check Story will point straight at them.
- **Search the existing issues** to see if someone has already reported it. If they have, add your
  details to that report instead of opening a new one.

## 2. Collect the details (automatic)

Either of these produces a ready-made report with your system information
(OpenNovella, Python, pygame and Pillow versions, and your operating system):

- **In the editor:** **Help → Report a Bug…**, then **Copy to clipboard**
- **From a terminal:**

  ```bash
  python -m opennovella bugreport "path/to/your/project"
  ```

If the game crashed, a **`crash.log`** was written to your project's `saves/` folder. The bug report
command includes it automatically when you pass your project folder.

## 3. Write the report

Open a new issue on the project's GitHub page using the **Bug report** template, or copy the template
below. Please include:

| Section | What to write |
|---|---|
| **Summary** | One sentence: *"Game crashes when a character with a GIF expression is hidden."* |
| **Steps to reproduce** | Exact clicks or commands, starting from opening the editor or game. |
| **Expected** | What you thought would happen. |
| **Actual** | What happened instead. Include error messages **word for word**. |
| **System info** | The output of `python -m opennovella bugreport`. |
| **Files** | If you can, attach a *small* project that shows the problem (zip the project folder, leaving out `saves/`), plus screenshots. |

### Template

~~~markdown
### Summary


### Steps to reproduce
1.
2.
3.

### Expected behaviour


### Actual behaviour (include any error text)


### Where does it happen?
- [ ] Editor
- [ ] Game / player
- [ ] Export
- [ ] Command line

### System information
(paste the output of `python -m opennovella bugreport` here)

### Crash log / screenshots / example project

~~~

## 4. Security problems

If you find a way for a story file to run code or access files on a player's computer, **please don't
post it publicly**. Contact the maintainers privately first so it can be fixed before it is announced.

---

## Fixing it yourself

Pull requests are very welcome! Please add a test in `tests/` that fails without your fix, and run:

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

---

*OpenNovella was created by Shawn Rapaz and Claude Code.*
