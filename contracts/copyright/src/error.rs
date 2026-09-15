use cosmwasm_std::StdError;
use thiserror::Error;

#[derive(Error, Debug, PartialEq)]
pub enum ContractError {
    #[error("{0}")]
    Std(#[from] StdError),

    #[error("Unauthorized")]
    Unauthorized {},

    #[error("Copyright ID already exists: {copyright_id}")]
    CopyrightExists { copyright_id: String },

    #[error("Copyright not found: {copyright_id}")]
    CopyrightNotFound { copyright_id: String },

    #[error("Invalid input: {reason}")]
    InvalidInput { reason: String },

    #[error("Insufficient fee. Expected: {expected}, Actual: {actual}")]
    InsufficientFee { expected: String, actual: String },
}
