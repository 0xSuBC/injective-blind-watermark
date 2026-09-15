use cosmwasm_std::{
    entry_point, to_json_binary, Binary, Deps, DepsMut, Env, MessageInfo, Response, StdResult,
    Uint64,
};
use cw2::set_contract_version;

use crate::error::ContractError;
use crate::msg::{
    ConfigResponse, CopyrightInfo, ExecuteMsg, InstantiateMsg, ListByOwnerResponse, QueryMsg,
};
use crate::state::{Config, CopyrightStored, BY_OWNER, CONFIG, COPYRIGHTS};

const CONTRACT_NAME: &str = "crates.io:copyright-contract";
const CONTRACT_VERSION: &str = env!("CARGO_PKG_VERSION");

#[cfg_attr(not(feature = "library"), entry_point)]
pub fn instantiate(
    deps: DepsMut,
    _env: Env,
    _info: MessageInfo,
    msg: InstantiateMsg,
) -> Result<Response, ContractError> {
    set_contract_version(deps.storage, CONTRACT_NAME, CONTRACT_VERSION)?;

    let admin = deps.api.addr_validate(&msg.admin)?;
    let cfg = Config {
        admin,
        register_fee: msg.register_fee,
        total_copyrights: Uint64::zero(),
    };
    CONFIG.save(deps.storage, &cfg)?;

    Ok(Response::new()
        .add_attribute("action", "instantiate")
        .add_attribute("contract", "copyright-registrar"))
}

#[cfg_attr(not(feature = "library"), entry_point)]
pub fn execute(
    deps: DepsMut,
    env: Env,
    info: MessageInfo,
    msg: ExecuteMsg,
) -> Result<Response, ContractError> {
    match msg {
        ExecuteMsg::RegisterCopyright {
            copyright_id,
            owner,
            original_hash,
            watermarked_hash,
            wm_bit_length,
            metadata,
            record_hash,
        } => register_copyright(
            deps,
            env,
            info,
            copyright_id,
            owner,
            original_hash,
            watermarked_hash,
            wm_bit_length,
            metadata,
            record_hash,
        ),
        ExecuteMsg::TransferCopyright {
            copyright_id,
            new_owner,
        } => transfer_copyright(deps, info, copyright_id, new_owner),
        ExecuteMsg::UpdateMetadata {
            copyright_id,
            metadata,
        } => update_metadata(deps, info, copyright_id, metadata),
    }
}

#[allow(clippy::too_many_arguments)]
fn register_copyright(
    deps: DepsMut,
    env: Env,
    info: MessageInfo,
    copyright_id: String,
    owner: String,
    original_hash: String,
    watermarked_hash: String,
    wm_bit_length: u32,
    metadata: Option<Binary>,
    record_hash: String,
) -> Result<Response, ContractError> {
    if COPYRIGHTS.has(deps.storage, &copyright_id) {
        return Err(ContractError::CopyrightExists { copyright_id });
    }

    if copyright_id.is_empty() {
        return Err(ContractError::InvalidInput {
            reason: "copyright_id cannot be empty".to_string(),
        });
    }
    if original_hash.len() != 64 {
        return Err(ContractError::InvalidInput {
            reason: "original_hash must be 64 char hex (sha256)".to_string(),
        });
    }
    if watermarked_hash.len() != 64 {
        return Err(ContractError::InvalidInput {
            reason: "watermarked_hash must be 64 char hex (sha256)".to_string(),
        });
    }
    if record_hash.len() != 64 {
        return Err(ContractError::InvalidInput {
            reason: "record_hash must be 64 char hex (sha256)".to_string(),
        });
    }

    let cfg = CONFIG.load(deps.storage)?;

    if let Some(fee) = &cfg.register_fee {
        let denom = fee.denom.as_str();
        let required: u128 = fee.amount.parse().unwrap_or(0);
        let sent = info
            .funds
            .iter()
            .find(|c| c.denom == denom)
            .map(|c| c.amount.u128())
            .unwrap_or(0);
        if sent < required {
            return Err(ContractError::InsufficientFee {
                expected: format!("{}{}", required, denom),
                actual: format!("{}{}", sent, denom),
            });
        }
    }

    let owner_addr = deps.api.addr_validate(&owner)?;

    let stored = CopyrightStored {
        copyright_id: copyright_id.clone(),
        owner: owner_addr.clone(),
        original_hash,
        watermarked_hash,
        wm_bit_length,
        metadata,
        record_hash,
        registered_at: env.block.time,
        registered_height: Uint64::from(env.block.height),
    };

    COPYRIGHTS.save(deps.storage, &copyright_id, &stored)?;
    BY_OWNER.save(deps.storage, (owner.as_str(), copyright_id.as_str()), &())?;

    CONFIG.update(deps.storage, |mut c| -> StdResult<_> {
        c.total_copyrights += Uint64::one();
        Ok(c)
    })?;

    Ok(Response::new()
        .add_attribute("action", "register_copyright")
        .add_attribute("copyright_id", copyright_id)
        .add_attribute("owner", owner)
        .add_attribute("sender", info.sender.to_string())
        .add_attribute("registered_height", env.block.height.to_string()))
}

fn transfer_copyright(
    deps: DepsMut,
    info: MessageInfo,
    copyright_id: String,
    new_owner: String,
) -> Result<Response, ContractError> {
    let mut stored = COPYRIGHTS
        .may_load(deps.storage, &copyright_id)?
        .ok_or_else(|| ContractError::CopyrightNotFound {
            copyright_id: copyright_id.clone(),
        })?;

    if info.sender != stored.owner {
        let cfg = CONFIG.load(deps.storage)?;
        if info.sender != cfg.admin {
            return Err(ContractError::Unauthorized {});
        }
    }

    let old_owner = stored.owner.to_string();
    let new_owner_addr = deps.api.addr_validate(&new_owner)?;

    BY_OWNER.remove(deps.storage, (old_owner.as_str(), copyright_id.as_str()));
    BY_OWNER.save(deps.storage, (new_owner.as_str(), copyright_id.as_str()), &())?;

    stored.owner = new_owner_addr;
    COPYRIGHTS.save(deps.storage, &copyright_id, &stored)?;

    Ok(Response::new()
        .add_attribute("action", "transfer_copyright")
        .add_attribute("copyright_id", copyright_id)
        .add_attribute("old_owner", old_owner)
        .add_attribute("new_owner", new_owner))
}

fn update_metadata(
    deps: DepsMut,
    info: MessageInfo,
    copyright_id: String,
    metadata: Option<Binary>,
) -> Result<Response, ContractError> {
    let mut stored = COPYRIGHTS
        .may_load(deps.storage, &copyright_id)?
        .ok_or_else(|| ContractError::CopyrightNotFound {
            copyright_id: copyright_id.clone(),
        })?;

    if info.sender != stored.owner {
        let cfg = CONFIG.load(deps.storage)?;
        if info.sender != cfg.admin {
            return Err(ContractError::Unauthorized {});
        }
    }

    stored.metadata = metadata;
    COPYRIGHTS.save(deps.storage, &copyright_id, &stored)?;

    Ok(Response::new()
        .add_attribute("action", "update_metadata")
        .add_attribute("copyright_id", copyright_id))
}

#[cfg_attr(not(feature = "library"), entry_point)]
pub fn query(deps: Deps, _env: Env, msg: QueryMsg) -> StdResult<Binary> {
    match msg {
        QueryMsg::GetCopyright { copyright_id } => to_json_binary(&query_copyright(deps, copyright_id)?),
        QueryMsg::ListByOwner {
            owner,
            limit,
            start_after,
        } => to_json_binary(&query_list_by_owner(deps, owner, limit, start_after)?),
        QueryMsg::Config {} => to_json_binary(&query_config(deps)?),
    }
}

fn query_copyright(deps: Deps, copyright_id: String) -> StdResult<CopyrightInfo> {
    let stored = COPYRIGHTS.load(deps.storage, &copyright_id)?;
    Ok(stored.into_info(None))
}

fn query_list_by_owner(
    deps: Deps,
    owner: String,
    limit: Option<u32>,
    start_after: Option<String>,
) -> StdResult<ListByOwnerResponse> {
    let limit = limit.unwrap_or(30) as usize;
    let start: &[u8] = start_after.as_deref().unwrap_or("").as_bytes();

    let prefix = BY_OWNER.prefix(owner.as_str());
    let items: StdResult<Vec<_>> = prefix
        .range(deps.storage, None, None, cosmwasm_std::Order::Ascending)
        .skip_while(|r| {
            r.as_ref()
                .map(|(k, _)| {
                    if start.is_empty() {
                        false
                    } else {
                        k.as_bytes() <= start
                    }
                })
                .unwrap_or(false)
        })
        .take(limit)
        .collect();

    let items = items?;
    let mut copyrights = Vec::with_capacity(items.len());
    for (cid, _) in items {
        if let Ok(stored) = COPYRIGHTS.load(deps.storage, &cid) {
            copyrights.push(stored.into_info(None));
        }
    }

    Ok(ListByOwnerResponse { owner, copyrights })
}

fn query_config(deps: Deps) -> StdResult<ConfigResponse> {
    let cfg = CONFIG.load(deps.storage)?;
    Ok(ConfigResponse {
        admin: cfg.admin.to_string(),
        register_fee: cfg.register_fee,
        total_copyrights: cfg.total_copyrights,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use cosmwasm_std::testing::{message_info, mock_dependencies, mock_env};
    use cosmwasm_std::{from_json, Addr, Coin, Uint128};
    use crate::msg::Coin as MsgCoin;

    const ADMIN: &str = "inj1adminadminadminadminadminadminadminadminad";
    const ALICE: &str = "inj1alicealicealicealicealicealicealicealiceal";
    const BOB: &str = "inj1bobbobbobbobbobbobbobbobbobbobbobbobbo";

    fn instantiate_with_fee(fee: Option<MsgCoin>) -> (
        cosmwasm_std::OwnedDeps<
            cosmwasm_std::MemoryStorage,
            cosmwasm_std::testing::MockApi,
            cosmwasm_std::testing::MockQuerier,
        >,
        cosmwasm_std::Env,
    ) {
        let mut deps = mock_dependencies();
        let env = mock_env();
        let info = message_info(&Addr::unchecked(ADMIN), &[]);
        let msg = InstantiateMsg { admin: ADMIN.to_string(), register_fee: fee };
        instantiate(deps.as_mut(), env.clone(), info, msg).unwrap();
        (deps, env)
    }

    fn sample_register(cid_suffix: &str) -> ExecuteMsg {
        ExecuteMsg::RegisterCopyright {
            copyright_id: format!("INJ-CPR-test0001-{cid_suffix}"),
            owner: ALICE.to_string(),
            original_hash: "a".repeat(64),
            watermarked_hash: "b".repeat(64),
            wm_bit_length: 264u32,
            metadata: Some(Binary::from_base64("eyJ0aXRsZSI6IkRlbW8ifQ==").unwrap()),
            record_hash: "c".repeat(64),
        }
    }

    #[test]
    fn test_instantiate_ok() {
        let (deps, env) = instantiate_with_fee(None);
        let cfg: ConfigResponse =
            from_json(query(deps.as_ref(), env, QueryMsg::Config {}).unwrap()).unwrap();
        assert_eq!(cfg.admin, ADMIN);
        assert_eq!(cfg.total_copyrights.u64(), 0);
    }

    #[test]
    fn test_register_and_query() {
        let (mut deps, env) = instantiate_with_fee(None);
        let info = message_info(&Addr::unchecked(ALICE), &[]);
        let msg = sample_register("0123456789abcdef");
        let res = execute(deps.as_mut(), env.clone(), info, msg).unwrap();
        assert_eq!(
            res.attributes.iter().find(|a| a.key == "action").unwrap().value,
            "register_copyright"
        );

        let q = QueryMsg::GetCopyright {
            copyright_id: "INJ-CPR-test0001-0123456789abcdef".to_string(),
        };
        let info: CopyrightInfo = from_json(query(deps.as_ref(), env, q).unwrap()).unwrap();
        assert_eq!(info.owner, ALICE);
        assert_eq!(info.wm_bit_length, 264u32);
        assert!(info.metadata.is_some());
    }

    #[test]
    fn test_duplicate_register_rejected() {
        let (mut deps, env) = instantiate_with_fee(None);
        let info = message_info(&Addr::unchecked(ALICE), &[]);
        let msg = sample_register("dupdupdupdupdupdup");
        execute(deps.as_mut(), env.clone(), info.clone(), msg.clone()).unwrap();
        let err = execute(deps.as_mut(), env, info, msg).unwrap_err();
        assert!(matches!(err, ContractError::CopyrightExists { .. }));
    }

    #[test]
    fn test_bad_hash_rejected() {
        let (mut deps, env) = instantiate_with_fee(None);
        let info = message_info(&Addr::unchecked(ALICE), &[]);
        let bad = ExecuteMsg::RegisterCopyright {
            copyright_id: "INJ-CPR-short-0000000000000000".to_string(),
            owner: ALICE.to_string(),
            original_hash: "tooshorthash".to_string(),
            watermarked_hash: "b".repeat(64),
            wm_bit_length: 10,
            metadata: None,
            record_hash: "c".repeat(64),
        };
        let err = execute(deps.as_mut(), env, info, bad).unwrap_err();
        assert!(matches!(err, ContractError::InvalidInput { .. }));
    }

    #[test]
    fn test_transfer_by_owner_ok() {
        let (mut deps, env) = instantiate_with_fee(None);
        let info_a = message_info(&Addr::unchecked(ALICE), &[]);
        execute(deps.as_mut(), env.clone(), info_a.clone(), sample_register("transfertest0001"))
            .unwrap();

        let tfer = ExecuteMsg::TransferCopyright {
            copyright_id: "INJ-CPR-test0001-transfertest0001".to_string(),
            new_owner: BOB.to_string(),
        };
        execute(deps.as_mut(), env.clone(), info_a, tfer).unwrap();

        let q = QueryMsg::GetCopyright {
            copyright_id: "INJ-CPR-test0001-transfertest0001".to_string(),
        };
        let info: CopyrightInfo = from_json(query(deps.as_ref(), env, q).unwrap()).unwrap();
        assert_eq!(info.owner, BOB);
    }

    #[test]
    fn test_transfer_unauthorized_rejected() {
        let (mut deps, env) = instantiate_with_fee(None);
        execute(
            deps.as_mut(),
            env.clone(),
            message_info(&Addr::unchecked(ALICE), &[]),
            sample_register("unauth00000000001"),
        )
        .unwrap();

        let tfer = ExecuteMsg::TransferCopyright {
            copyright_id: "INJ-CPR-test0001-unauth00000000001".to_string(),
            new_owner: BOB.to_string(),
        };
        let err = execute(deps.as_mut(), env, message_info(&Addr::unchecked(BOB), &[]), tfer).unwrap_err();
        assert!(matches!(err, ContractError::Unauthorized {}));
    }

    #[test]
    fn test_list_by_owner() {
        let (mut deps, env) = instantiate_with_fee(None);
        for i in 0..2u32 {
            let msg = ExecuteMsg::RegisterCopyright {
                copyright_id: format!("INJ-CPR-aaaaaaaa-listowner{i:02}"),
                owner: ALICE.to_string(),
                original_hash: format!("{i:0<64}"),
                watermarked_hash: format!("{i:0<64}"),
                wm_bit_length: 200 + i,
                metadata: None,
                record_hash: format!("{i:0<64}"),
            };
            execute(
                deps.as_mut(),
                env.clone(),
                message_info(&Addr::unchecked(ALICE), &[]),
                msg,
            )
            .unwrap();
        }
        let msg_bob = ExecuteMsg::RegisterCopyright {
            copyright_id: "INJ-CPR-bbbbbbbb-bobsonly00001".to_string(),
            owner: BOB.to_string(),
            original_hash: "9".repeat(64),
            watermarked_hash: "9".repeat(64),
            wm_bit_length: 111,
            metadata: None,
            record_hash: "9".repeat(64),
        };
        execute(
            deps.as_mut(),
            env.clone(),
            message_info(&Addr::unchecked(BOB), &[]),
            msg_bob,
        )
        .unwrap();

        let resp: ListByOwnerResponse = from_json(
            query(
                deps.as_ref(),
                env.clone(),
                QueryMsg::ListByOwner {
                    owner: ALICE.to_string(),
                    limit: None,
                    start_after: None,
                },
            )
            .unwrap(),
        )
        .unwrap();
        assert_eq!(resp.copyrights.len(), 2);

        let resp: ListByOwnerResponse = from_json(
            query(
                deps.as_ref(),
                env,
                QueryMsg::ListByOwner {
                    owner: BOB.to_string(),
                    limit: None,
                    start_after: None,
                },
            )
            .unwrap(),
        )
        .unwrap();
        assert_eq!(resp.copyrights.len(), 1);
        assert_eq!(resp.copyrights[0].wm_bit_length, 111);
    }

    #[test]
    fn test_register_fee() {
        let fee = MsgCoin { denom: "inj".into(), amount: "1000000".into() };
        let (mut deps, env) = instantiate_with_fee(Some(fee));

        // 不付费 → 拒绝
        let info_free = message_info(&Addr::unchecked(ALICE), &[]);
        let err = execute(deps.as_mut(), env.clone(), info_free, sample_register("feetest00000001"))
            .unwrap_err();
        assert!(matches!(err, ContractError::InsufficientFee { .. }));

        // 付费 → 成功
        let paid = Coin::new(Uint128::new(1_000_000u128), "inj");
        let info_paid = message_info(&Addr::unchecked(ALICE), &[paid]);
        execute(deps.as_mut(), env, info_paid, sample_register("feetest00000001")).unwrap();
    }

    #[test]
    fn test_update_metadata() {
        let (mut deps, env) = instantiate_with_fee(None);
        execute(
            deps.as_mut(),
            env.clone(),
            message_info(&Addr::unchecked(ALICE), &[]),
            sample_register("updatemeta000001"),
        )
        .unwrap();

        let new_meta = Binary::from_base64("eyJ0aXRsZSI6Ik5ldyJ9").unwrap();
        let msg = ExecuteMsg::UpdateMetadata {
            copyright_id: "INJ-CPR-test0001-updatemeta000001".to_string(),
            metadata: Some(new_meta.clone()),
        };
        execute(
            deps.as_mut(),
            env.clone(),
            message_info(&Addr::unchecked(ALICE), &[]),
            msg,
        )
        .unwrap();

        let q = QueryMsg::GetCopyright {
            copyright_id: "INJ-CPR-test0001-updatemeta000001".to_string(),
        };
        let info: CopyrightInfo = from_json(query(deps.as_ref(), env, q).unwrap()).unwrap();
        assert_eq!(info.metadata, Some(new_meta));
    }
}
