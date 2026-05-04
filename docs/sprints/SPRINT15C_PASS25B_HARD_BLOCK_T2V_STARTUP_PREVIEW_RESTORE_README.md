# Sprint 15C Pass 25B — Hard Block T2V Startup Preview Restore

Adds a startup suppression flag so T2V does not automatically bind the previously generated video during app launch or initial page creation.

The first T2V page render now shows an empty video preview state. Preview binding is re-enabled only when a video is explicitly shown by generation, history, or queue action.

This also keeps the Pass 25 distilled-output preference in T2V History.
