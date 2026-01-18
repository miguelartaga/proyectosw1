import React from "react";
import "./App.css";
import ChatPanel from "./components/ChatPanel";
import DiagramCanvas from "./components/DiagramCanvas";

const App: React.FC = () => {
    return (
        <div className="app-shell">
            <header className="app-header">
                <div className="app-header__title">UML/ER Editor</div>
            </header>

            <div className="app-container">
                <div className="sidebar">
                    <ChatPanel />
                </div>

                <div className="canvas-container">
                    <DiagramCanvas />
                </div>
            </div>
        </div>
    );
};

export default App;
