-- Create the watchlists table
CREATE TABLE watchlists (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    symbol TEXT NOT NULL,
    added_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, symbol) -- Prevent duplicate symbols for the same user
);

-- Enable Row Level Security (RLS)
ALTER TABLE watchlists ENABLE ROW LEVEL SECURITY;

-- Create policy so users can only SELECT their own watchlists
CREATE POLICY "Users can view their own watchlist"
ON watchlists FOR SELECT
USING (auth.uid() = user_id);

-- Create policy so users can only INSERT into their own watchlists
CREATE POLICY "Users can insert into their own watchlist"
ON watchlists FOR INSERT
WITH CHECK (auth.uid() = user_id);

-- Create policy so users can only DELETE from their own watchlists
CREATE POLICY "Users can delete from their own watchlist"
ON watchlists FOR DELETE
USING (auth.uid() = user_id);
