package com.ex.web;

/** Base des actions de l'interface d'administration. */
public abstract class BaseAction {
    protected String message;

    public String execute() {
        return "success";
    }

    protected void addError(String text) {
        this.message = text;
    }
}
