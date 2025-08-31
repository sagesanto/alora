CREATE TABLE IF NOT EXISTS metadata (
    CandidateID INTEGER NOT NULL,
    key TEXT,
    value TEXT,
    FOREIGN KEY (CandidateID) REFERENCES Candidates(ID) ON DELETE CASCADE,
    PRIMARY KEY (CandidateID, key)
);