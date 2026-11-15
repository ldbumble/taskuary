// IS THIS THE DEMO (taskuary --demo, taskuary.com/demo): said once by the page as it opens (TaskHubPage useDemo), read by whatever words what a
// press did there - a Send that was played says so (sentLine). A module's own flag, so a function of plain words can ask without a hook.
let on = false;
export const markDemo = (v) => { on = !!v; };
export const inDemo = () => on;
